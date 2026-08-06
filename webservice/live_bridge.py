"""main.py 감지 파이프라인 → 다온 웹플랫폼 실시간 중계 어댑터.

webapp_server.WebAppServer 와 같은 인터페이스(start/push_pose/push_fall/push_reset/stop)를
제공하는 드롭인이다. 자체 WebSocket 서버를 띄우는 대신 플랫폼의 POST /api/live/event 로
이벤트를 밀어넣고, 플랫폼이 브라우저(/live)로 브로드캐스트한다.

중계 실패가 감지 파이프라인을 죽이면 안 되므로 push_* 는 어떤 예외도 밖으로 던지지 않는다.
와이어 메시지 형식은 webservice.live 빌더를 그대로 써서 합성 푸셔·프런트와 일치시킨다.
"""

import os
import time

from webservice import live


class LiveBridge:
    def __init__(self, url, token=None, client=None, timeout=1.0):
        base = url.rstrip("/")
        self._event_url = base + "/api/live/event"
        self._frame_url = base + "/api/live/frame"
        self._control_url = base + "/api/live/control"
        self._health_url = base + "/api/health"
        self._token = token or os.environ.get("LIVE_INGEST_TOKEN", "daon-live")
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

    def start(self):
        """플랫폼 도달 여부를 확인한다. webapp_server.start() 처럼 bool 을 반환."""
        try:
            ok = self._client.get(self._health_url).status_code == 200
        except Exception:
            ok = False
        if ok:
            print(f"[중계] 플랫폼 연결됨 - 감지 결과를 {self._event_url} 로 중계합니다.")
        else:
            print(f"[중계] 경고: 플랫폼에 연결할 수 없습니다 ({self._health_url}) - "
                  "중계 없이 진행합니다.")
        return ok

    def _post(self, message):
        try:
            self._client.post(self._event_url, json=message,
                              headers={"X-Live-Token": self._token})
        except Exception:
            pass   # 중계 실패는 조용히 무시 - 감지 파이프라인이 우선

    def push_pose(self, landmarks, shape, risk_score, consecutive, persistence):
        now = time.monotonic()
        if now - self._last_pose < self.pose_min_interval:
            return
        self._last_pose = now
        self._post(live.pose_message(landmarks, shape, risk_score,
                                     consecutive, persistence))

    def should_pause(self):
        """브라우저가 '카메라를 잠시 끊어달라'고 했는지.

        매 프레임 물어보면 요청이 낭비되므로 0.5초에 한 번만 확인하고, 그 사이에는
        마지막 답을 재사용한다. 서버에 못 닿으면 직전 상태를 유지한다 — 네트워크가
        잠깐 끊겼다고 카메라가 제멋대로 켜지거나 꺼지면 안 된다.
        """
        now = time.monotonic()
        if now - self._last_control < self.control_min_interval:
            return self._paused
        self._last_control = now
        try:
            r = self._client.get(self._control_url,
                                 headers={"X-Live-Token": self._token})
            if r.status_code == 200:
                self._paused = bool(r.json().get("paused", False))
        except Exception:
            pass
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
            self._client.post(self._frame_url, content=buf.tobytes(),
                              headers={"X-Live-Token": self._token,
                                       "Content-Type": "image/jpeg"})
        except Exception:
            pass   # 중계 실패는 조용히 무시 - 감지 파이프라인이 우선

    def push_fall(self, tiles, rows, cols, direction_deg):
        self._post(live.fall_message(tiles, rows, cols, direction_deg))

    def push_reset(self):
        self._post(live.reset_message())

    def stop(self):
        if self._own_client:
            try:
                self._client.close()
            except Exception:
                pass
