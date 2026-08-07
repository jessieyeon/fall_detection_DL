"""전시 중 부하를 눈으로 보기 위한 최소 카운터.

프로메테우스 같은 걸 붙일 상황이 아니다(단일 인스턴스, 2주짜리 전시). 필요한 것은
"지금 몇 개가 돌고 있고, 거절이 나고 있고, 느려지고 있나" 세 가지뿐이라 메모리
카운터로 충분하다.

ponytail: 프로세스 안에서만 유효하다. 재시작하면 0 부터. 워커를 여러 개 띄우면
숫자가 갈라지므로 그때는 외부 수집기로 옮긴다(지금은 워커 1개 고정 — 분석 잡
저장소도 같은 이유로 인메모리다).
"""

import threading
import time

SLOW_SECONDS = 3.0          # 이보다 오래 걸린 요청은 따로 센다


class Counter:
    def __init__(self):
        self.started = time.monotonic()
        self.total = 0
        self.by_status = {}
        self.slow = 0
        self._lock = threading.Lock()

    def record(self, status_code, seconds):
        with self._lock:
            self.total += 1
            key = str(status_code)
            self.by_status[key] = self.by_status.get(key, 0) + 1
            if seconds >= SLOW_SECONDS:
                self.slow += 1

    def snapshot(self):
        with self._lock:
            return {"uptime_s": round(time.monotonic() - self.started, 1),
                    "requests": {"total": self.total,
                                 "by_status": dict(self.by_status)},
                    "slow_requests": self.slow}


counter = Counter()
