"""부하 시뮬레이터의 통계 계산 — 리포트 숫자가 틀리면 잘못된 결론을 내린다.

특히 503(한도 초과 거절)을 실패로 세면 "서버가 터졌다"고 오판하게 된다.
그건 설계대로 동작하고 있다는 증거다.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))
from load_test import percentile, summarize                      # noqa: E402


def test_percentile_basic():
    xs = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    assert percentile(xs, 50) == 5.5
    assert percentile(xs, 95) == 9.55


def test_percentile_single_value():
    assert percentile([2.0], 95) == 2.0


def test_percentile_empty_is_zero():
    assert percentile([], 95) == 0.0


def test_summarize_counts_rejection_separately_from_failure():
    s = summarize([(200, 0.1), (200, 0.2), (503, 0.01), (500, 0.3)])
    assert s["total"] == 4
    assert s["ok"] == 2
    assert s["rejected"] == 1          # 503 은 '정상적인 거절'이라 따로 센다
    assert s["failed"] == 1            # 500 은 진짜 실패


def test_summarize_counts_timeouts_as_failure():
    """599 는 우리가 붙인 코드 — 타임아웃/연결 실패."""
    s = summarize([(200, 0.1), (599, 15.0)])
    assert s["failed"] == 1
    assert s["ok"] == 1


def test_summarize_empty():
    s = summarize([])
    assert s["total"] == 0 and s["p95"] == 0.0 and s["max"] == 0.0
