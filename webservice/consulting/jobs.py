"""인메모리 분석 잡 저장소 + 백그라운드 스레드 러너.

ponytail: 단일 프로세스 데모 한정. 여러 워커/재시작 간 공유가 필요하면
잡 상태를 DB나 Redis로 옮긴다.
"""

import threading
import uuid

_jobs = {}
_lock = threading.Lock()


def create_job():
    job_id = uuid.uuid4().hex
    with _lock:
        _jobs[job_id] = {"status": "pending", "report_id": None, "error": None}
    return job_id


def _set(job_id, **fields):
    with _lock:
        _jobs[job_id].update(fields)


def run_in_background(job_id, fn):
    def worker():
        try:
            report_id = fn()
            _set(job_id, status="done", report_id=report_id)
        except Exception as exc:                      # noqa: BLE001 - 잡 실패를 상태로 보고
            _set(job_id, status="error", error=str(exc))
    threading.Thread(target=worker, daemon=True).start()


def get_job(job_id):
    with _lock:
        j = _jobs.get(job_id)
        return dict(j) if j else None
