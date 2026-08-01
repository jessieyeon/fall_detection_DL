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
        self._health_url = base + "/api/health"
        self._token = token or os.environ.get("LIVE_INGEST_TOKEN", "daon-live")
        self._own_client = client is None
        if client is None:
            import httpx  # 지연 임포트 — 중계를 안 쓰면 httpx 를 강제하지 않는다
            client = httpx.Client(timeout=timeout)
        self._client = client
        self._last_pose = 0.0
        self.pose_min_interval = 1.0 / 20   # 포즈 ~20fps 제한 (webapp_server 와 동일)

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
