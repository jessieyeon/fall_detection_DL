"""동시 분석 제한 테스트.

전시 중 동시 업로드가 몰렸을 때 스레드가 무한정 쌓이면 서버가 통째로 멎는다.
거절이 무한 대기보다 낫다는 설계를 고정한다.
"""

import threading
import time

import pytest

from webservice.consulting import jobs


@pytest.fixture(autouse=True)
def reset():
    """모듈 전역 상태를 테스트마다 초기화한다."""
    jobs._jobs.clear()
    jobs._inflight = 0
    jobs._slots = threading.BoundedSemaphore(jobs.MAX_CONCURRENT)
    yield
    jobs._jobs.clear()
    jobs._inflight = 0


def _wait_until(pred, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.01)
    return False


def test_job_runs_and_reports_result():
    jid = jobs.create_job()
    jobs.run_in_background(jid, lambda: 42)
    assert _wait_until(lambda: jobs.get_job(jid)["status"] == "done")
    assert jobs.get_job(jid)["report_id"] == 42


def test_failure_is_reported_as_status_not_crash():
    jid = jobs.create_job()

    def boom():
        raise ValueError("분석 실패")
    jobs.run_in_background(jid, boom)

    assert _wait_until(lambda: jobs.get_job(jid)["status"] == "error")
    assert "분석 실패" in jobs.get_job(jid)["error"]


def test_complete_marks_done_without_running_anything():
    """캐시 적중 경로 — 분석 없이 완료 상태가 되어야 한다."""
    jid = jobs.create_job()
    jobs.complete(jid, 7)
    j = jobs.get_job(jid)
    assert j["status"] == "done" and j["report_id"] == 7


def test_concurrency_is_capped():
    """동시에 도는 분석이 MAX_CONCURRENT 를 넘지 않아야 한다."""
    running = []
    peak = [0]
    lock = threading.Lock()
    release = threading.Event()

    def slow():
        with lock:
            running.append(1)
            peak[0] = max(peak[0], len(running))
        release.wait(2.0)
        with lock:
            running.pop()
        return 1

    ids = [jobs.create_job() for _ in range(jobs.MAX_CONCURRENT + 2)]
    for jid in ids:
        jobs.run_in_background(jid, slow)

    _wait_until(lambda: peak[0] >= jobs.MAX_CONCURRENT)
    release.set()
    assert peak[0] <= jobs.MAX_CONCURRENT, f"동시 {peak[0]}개가 돌았다"
    _wait_until(lambda: all(jobs.get_job(i)["status"] == "done" for i in ids))


def test_rejects_when_queue_is_full():
    """대기열이 차면 조용히 쌓지 말고 명확히 거절해야 한다."""
    release = threading.Event()

    def blocked():
        release.wait(3.0)
        return 1

    accepted = []
    try:
        for _ in range(jobs.MAX_INFLIGHT):
            jid = jobs.create_job()
            jobs.run_in_background(jid, blocked)
            accepted.append(jid)

        with pytest.raises(jobs.TooBusy) as exc:
            jobs.run_in_background(jobs.create_job(), blocked)
        assert "잠시 후" in str(exc.value)
    finally:
        release.set()
    _wait_until(lambda: all(jobs.get_job(i)["status"] == "done" for i in accepted))


def test_inflight_returns_to_zero():
    """작업이 끝나면 자리를 반납해야 한다 — 안 그러면 서서히 막힌다."""
    ids = [jobs.create_job() for _ in range(3)]
    for jid in ids:
        jobs.run_in_background(jid, lambda: 1)
    assert _wait_until(lambda: jobs.stats()["inflight"] == 0)


def test_failed_job_also_releases_its_slot():
    ids = [jobs.create_job() for _ in range(3)]
    for jid in ids:
        jobs.run_in_background(jid, lambda: 1 / 0)
    assert _wait_until(lambda: jobs.stats()["inflight"] == 0)
