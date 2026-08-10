"""main.py 감지 파이프라인 → 다온 웹플랫폼 실시간 중계 어댑터.

webapp_server.WebAppServer 와 같은 인터페이스(start/push_pose/push_fall/push_reset/stop)를
제공하는 드롭인이다. 자체 WebSocket 서버를 띄우는 대신 플랫폼의 POST /api/live/event 로
이벤트를 밀어넣고, 플랫폼이 브라우저(/live)로 브로드캐스트한다.

중계 실패가 감지 파이프라인을 죽이면 안 되므로 push_* 는 어떤 예외도 밖으로 던지지 않는다.
와이어 메시지 형식은 webservice.live 빌더를 그대로 써서 합성 푸셔·프런트와 일치시킨다.

**전송은 별도 스레드에서 한다.** push_* 는 보낼 것을 큐에 놓고 즉시 돌아온다.
예전에는 영상 루프 안에서 곧바로 POST 를 했는데, 로컬(localhost, 왕복 1ms)에서는
티가 안 나다가 배포 서버로 바꾸는 순간 화면이 뚝뚝 끊겼다. 인터넷 왕복이 100ms 라면
포즈 20fps + 영상 12fps 를 보내는 데만 1초에 3초가 필요하다 — 애초에 불가능하고,
그만큼 카메라를 못 읽는다. 판정 속도가 네트워크 지연에 묶여서는 안 된다.
"""

import os
import threading
import time
from collections import deque

from webservice import live


class LiveBridge:
    def __init__(self, url, token=None, client=None, timeout=1.0, device_key=None):
        base = url.rstrip("/")
        self._event_url = base + "/api/live/event"
        self._frame_url = base + "/api/live/frame"
        self._control_url = base + "/api/live/control"
        self._health_url = base + "/api/health"
        self._token = token or os.environ.get("LIVE_INGEST_TOKEN", "daon-live")
        # 이 카메라가 자기를 밝히는 값. 관리자 화면의 '주변 카메라 찾기'가 이걸로
        # 채워지고, 등록된 카메라는 온라인으로 바뀐다. 없으면 익명으로 중계한다 —
        # device_key 없이 띄우던 기존 방식이 그대로 돌아야 한다.
        self._device_key = device_key or os.environ.get("DAON_DEVICE_KEY", "")
        self._own_client = client is None
        if client is None:
            import httpx  # 지연 임포트 — 중계를 안 쓰면 httpx 를 강제하지 않는다
            client = httpx.Client(timeout=timeout)
        self._client = client
        self._last_pose = 0.0
        self._last_frame = 0.0
        self._last_control = 0.0
        self._paused = False
        self.control_min_interval = 0.5   # 제어 신호 확인 주기(초)
        self.pose_min_interval = 1.0 / 20   # 포즈 ~20fps 제한 (webapp_server 와 동일)

        # 영상은 포즈보다 훨씬 무겁다. 프레임률과 크기를 따로 제한한다.
        self.frame_min_interval = 1.0 / float(os.environ.get("DAON_STREAM_FPS", "12"))
        self.frame_width = int(os.environ.get("DAON_STREAM_WIDTH", "480"))
        self.frame_quality = int(os.environ.get("DAON_STREAM_QUALITY", "65"))

        # --- 전송 스레드 ---
        # 포즈와 영상은 '가장 최신 한 개'만 들고 있다가 보낸다. 네트워크가 느리면
        # 밀린 것을 따라 보내봐야 이미 지난 장면이라 의미가 없고, 쌓이면 지연만
        # 커진다. 반대로 낙상·리셋은 그 순간에만 의미가 있는 신호라 버리지 않는다.
        self._lock = threading.Lock()
        self._pending_pose = None
        self._pending_frame = None
        self._pending_events = deque(maxlen=32)
        self._wake = threading.Event()
        self._stopping = False
        self._thread = None

    def start(self):
        """플랫폼 도달 여부를 확인한다. webapp_server.start() 처럼 bool 을 반환."""
        try:
            ok = self._client.get(self._health_url).status_code == 200
        except Exception:
            ok = False
        if ok:
            self._thread = threading.Thread(target=self._run, name="live-bridge",
                                            daemon=True)
            self._thread.start()
            who = f" (기기 {self._device_key})" if self._device_key else ""
            print(f"[중계] 플랫폼 연결됨{who} - 감지 결과를 {self._event_url} 로 중계합니다.")
        else:
            print(f"[중계] 경고: 플랫폼에 연결할 수 없습니다 ({self._health_url}) - "
                  "중계 없이 진행합니다.")
        return ok

    def _headers(self, **extra):
        h = {"X-Live-Token": self._token, **extra}
        if self._device_key:
            h["X-Device-Key"] = self._device_key
        return h

    # --- 전송 (스레드가 있으면 큐에, 없으면 그 자리에서) ---

    @property
    def _threaded(self):
        return self._thread is not None and self._thread.is_alive()

    def _send_event(self, message):
        try:
            self._client.post(self._event_url, json=message, headers=self._headers())
        except Exception:
            pass   # 중계 실패는 조용히 무시 - 감지 파이프라인이 우선

    def _send_frame(self, jpeg):
        try:
            self._client.post(self._frame_url, content=jpeg,
                              headers=self._headers(**{"Content-Type": "image/jpeg"}))
        except Exception:
            pass

    def _post(self, message):
        """낙상·리셋처럼 버리면 안 되는 이벤트."""
        if not self._threaded:
            self._send_event(message)
            return
        with self._lock:
            self._pending_events.append(message)
        self._wake.set()

    def _run(self):
        """전송 스레드. 밀린 것은 최신 것만 남기고 버린다."""
        while not self._stopping:
            self._wake.wait(0.1)
            self._wake.clear()

            while not self._stopping:
                with self._lock:
                    event = self._pending_events.popleft() if self._pending_events else None
                if event is None:
                    break
                self._send_event(event)

            with self._lock:
                pose, self._pending_pose = self._pending_pose, None
                frame, self._pending_frame = self._pending_frame, None
            if pose is not None:
                self._send_event(pose)
            if frame is not None:
                self._send_frame(frame)

            self._refresh_control()

    def push_pose(self, landmarks, shape, risk_score, consecutive, persistence):
        now = time.monotonic()
        if now - self._last_pose < self.pose_min_interval:
            return
        self._last_pose = now
        message = live.pose_message(landmarks, shape, risk_score,
                                    consecutive, persistence)
        if not self._threaded:
            self._send_event(message)
            return
        with self._lock:
            self._pending_pose = message      # 밀려 있던 것은 버린다
        self._wake.set()

    def _refresh_control(self):
        """일시정지 여부를 서버에 물어 캐시에 넣는다. 전송 스레드에서만 부른다."""
        now = time.monotonic()
        if now - self._last_control < self.control_min_interval:
            return
        self._last_control = now
        try:
            r = self._client.get(self._control_url, headers=self._headers())
            if r.status_code == 200:
                self._paused = bool(r.json().get("paused", False))
        except Exception:
            pass

    def should_pause(self):
        """브라우저가 '카메라를 잠시 끊어달라'고 했는지.

        영상 루프에서 매 프레임 불리므로 절대 블로킹하지 않는다. 실제 조회는
        전송 스레드가 0.5초에 한 번 하고, 여기서는 마지막 답만 돌려준다.
        서버에 못 닿으면 직전 상태를 유지한다 — 네트워크가 잠깐 끊겼다고 카메라가
        제멋대로 켜지거나 꺼지면 안 된다.

        스레드가 없으면(테스트 등) 예전처럼 그 자리에서 조회한다.
        """
        if not self._threaded:
            self._refresh_control()
        return self._paused

    def push_frame(self, image):
        """카메라 프레임(BGR ndarray)을 JPEG 로 줄여 중계한다.

        스켈레톤 좌표만 보내면 브라우저에는 검은 배경 위의 선만 보인다. 실제
        영상이 함께 보여야 카메라가 무엇을 보고 있는지, 오검출이 왜 났는지
        확인할 수 있다.

        원본 해상도를 그대로 보내면 대역폭을 크게 먹으므로 긴 변을 480px 로
        줄이고 JPEG 품질을 낮춘다. 판정은 이미 원본으로 끝난 뒤라 화질이
        결과에 영향을 주지 않는다.
        """
        now = time.monotonic()
        if now - self._last_frame < self.frame_min_interval:
            return
        self._last_frame = now
        try:
            import cv2
            h, w = image.shape[:2]
            if w > self.frame_width:
                scale = self.frame_width / w
                image = cv2.resize(image, (self.frame_width, int(round(h * scale))),
                                   interpolation=cv2.INTER_AREA)
            ok, buf = cv2.imencode(".jpg", image,
                                   [int(cv2.IMWRITE_JPEG_QUALITY), self.frame_quality])
            if not ok:
                return
            jpeg = buf.tobytes()
        except Exception:
            return     # 인코딩 실패는 조용히 무시 - 감지 파이프라인이 우선

        if not self._threaded:
            self._send_frame(jpeg)
            return
        with self._lock:
            self._pending_frame = jpeg        # 밀려 있던 것은 버린다
        self._wake.set()

    def push_fall(self, tiles, rows, cols, direction_deg):
        self._post(live.fall_message(tiles, rows, cols, direction_deg))

    def push_reset(self):
        self._post(live.reset_message())

    def stop(self):
        # 스레드를 먼저 세운다. 클라이언트를 닫아둔 채로 스레드가 살아 있으면
        # 이미 닫힌 소켓에 쓰려 든다.
        self._stopping = True
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._own_client:
            try:
                self._client.close()
            except Exception:
                pass
