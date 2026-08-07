"""트래픽 수치 엔드포인트 — 전시 중에 부하를 눈으로 볼 수 있어야 한다.

/api/health 의 {"status":"ok"} 만으로는 "지금 몇 명이 붙어 있고 분석이 밀리는지"를
알 수 없다. 이미 있는 카운터를 한 곳에 모아 노출한다.
"""

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    dbfile = os.path.join(tmp_path, "t.db")
    monkeypatch.setattr("webservice.db.DB_PATH", dbfile)
    from webservice import db, app as app_module
    db.init_db(dbfile)
    return TestClient(app_module.app)


def test_metrics_shape(client):
    r = client.get("/api/metrics")
    assert r.status_code == 200
    m = r.json()
    assert m["uptime_s"] >= 0
    assert "total" in m["requests"]
    assert m["jobs"]["max_inflight"] >= 1
    assert m["live"]["self_max"] >= 1


def test_requests_are_counted(client):
    before = client.get("/api/metrics").json()["requests"]["total"]
    client.get("/api/health")
    after = client.get("/api/metrics").json()["requests"]["total"]
    assert after > before


def test_status_codes_are_counted(client):
    client.get("/api/consulting/reports")        # 로그인 안 했으니 401
    m = client.get("/api/metrics").json()
    assert any(int(k) >= 400 for k in m["requests"]["by_status"])


def test_live_numbers_match_live_status(client):
    """같은 값을 두 엔드포인트가 다르게 말하면 어느 쪽도 믿을 수 없다."""
    status = client.get("/api/live/status").json()
    live = client.get("/api/metrics").json()["live"]
    assert live["frames"] == status["frames"]
    assert live["viewers"] == status["viewers"]


def test_slow_requests_counted():
    """느린 요청은 따로 센다 — 인스턴스가 부족해지는 첫 신호다."""
    from webservice import metrics
    c = metrics.Counter()
    c.record(200, metrics.SLOW_SECONDS + 0.1)
    c.record(200, 0.01)
    snap = c.snapshot()
    assert snap["slow_requests"] == 1
    assert snap["requests"]["total"] == 2
