"""인메모리 분석 잡 저장소 + 백그라운드 스레드 러너.

ponytail: 단일 프로세스 데모 한정. 여러 워커/재시작 간 공유가 필요하면
잡 상태를 DB나 Redis로 옮긴다. (그래서 uvicorn 워커를 여러 개 띄우면 안 된다 —
폴링이 다른 워커로 가면 잡을 못 찾는다.)

## 동시 실행 제한

YOLO 추론은 CPU 를 크게 쓴다. 전시 중 동시 업로드가 몰리면 스레드가 무한정
쌓여 메모리와 CPU 가 동시에 고갈되고, 결국 아무 요청도 끝나지 않는다.
두 겹으로 막는다.

  · `MAX_CONCURRENT` — 실제로 동시에 도는 분석 수 (세마포어)
  · `MAX_INFLIGHT` — 대기까지 포함한 총량. 넘으면 받지 않고 즉시 거절한다

거절이 무한 대기보다 낫다. 사용자는 "지금 혼잡하니 잠시 후"라는 답을 받으면
다시 시도하지만, 응답 없이 기다리게 하면 그냥 떠난다.
"""

import os
import threading
import uuid

MAX_CONCURRENT = int(os.environ.get("DAON_MAX_CONCURRENT_JOBS", "2"))
MAX_INFLIGHT = int(os.environ.get("DAON_MAX_INFLIGHT_JOBS", "8"))

_jobs = {}
_lock = threading.Lock()
_slots = threading.BoundedSemaphore(MAX_CONCURRENT)
_inflight = 0


class TooBusy(RuntimeError):
    """대기열이 가득 찼다."""


def create_job():
    job_id = uuid.uuid4().hex
    with _lock:
        _jobs[job_id] = {"status": "pending", "report_id": None, "error": None}
    return job_id


def _set(job_id, **fields):
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(fields)


def complete(job_id, report_id):
    """분석 없이 즉시 끝난 잡(캐시 적중)을 완료로 표시한다.

    프런트는 job_id → status 폴링 흐름을 그대로 쓰므로, 캐시 적중도 같은
    모양으로 돌려줘야 클라이언트 코드가 갈라지지 않는다.
    """
    _set(job_id, status="done", report_id=report_id)
    return job_id


def run_in_background(job_id, fn):
    """분석을 백그라운드에서 돌린다. 대기열이 가득 차면 TooBusy."""
    global _inflight
    with _lock:
        if _inflight >= MAX_INFLIGHT:
            raise TooBusy(
                "지금 분석 요청이 많아 처리할 수 없습니다. 잠시 후 다시 시도해 주세요.")
        _inflight += 1

    def worker():
        global _inflight
        try:
            with _slots:                       # 동시 실행 수 제한
                report_id = fn()
            _set(job_id, status="done", report_id=report_id)
        except Exception as exc:               # noqa: BLE001 - 잡 실패를 상태로 보고
            _set(job_id, status="error", error=str(exc))
        finally:
            with _lock:
                _inflight -= 1

    threading.Thread(target=worker, daemon=True).start()


def get_job(job_id):
    with _lock:
        j = _jobs.get(job_id)
        return dict(j) if j else None


def stats():
    """현재 부하. 운영 중 확인용."""
    with _lock:
        return {"inflight": _inflight, "max_inflight": MAX_INFLIGHT,
                "max_concurrent": MAX_CONCURRENT, "known_jobs": len(_jobs)}
