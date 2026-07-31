import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def env(tmp_path, monkeypatch):
    dbfile = os.path.join(tmp_path, "t.db")
    monkeypatch.setattr("webservice.db.DB_PATH", dbfile)
    from webservice import db, auth, app as app_module
    db.init_db(dbfile)
    conn = db.connect(dbfile)
    auth.create_user(conn, "s@d.com", "pw", "senior", "어르신")
    auth.create_user(conn, "g@d.com", "pw", "guardian", "보호자")
    conn.close()
    return app_module.app


def _client(app):
    return TestClient(app)


def test_full_pairing_flow(env):
    senior = _client(env)
    senior.post("/api/auth/login", json={"email": "s@d.com", "password": "pw"})
    code = senior.post("/api/guardian/code").json()["code"]

    guardian = _client(env)
    guardian.post("/api/auth/login", json={"email": "g@d.com", "password": "pw"})
    r = guardian.post("/api/guardian/redeem", json={"code": code})
    assert r.status_code == 200 and r.json()["senior"]["name"] == "어르신"

    wards = guardian.get("/api/guardian/wards").json()
    assert len(wards) == 1 and wards[0]["name"] == "어르신"
    assert wards[0]["risk_level"] is None          # 아직 설문 없음

    guardians = senior.get("/api/guardian/list").json()
    assert len(guardians) == 1 and guardians[0]["name"] == "보호자"


def test_code_endpoint_rejects_guardian(env):
    guardian = _client(env)
    guardian.post("/api/auth/login", json={"email": "g@d.com", "password": "pw"})
    assert guardian.post("/api/guardian/code").status_code == 403


def test_redeem_rejects_senior(env):
    senior = _client(env)
    senior.post("/api/auth/login", json={"email": "s@d.com", "password": "pw"})
    assert senior.post("/api/guardian/redeem", json={"code": "000000"}).status_code == 403


def test_redeem_bad_code_400(env):
    guardian = _client(env)
    guardian.post("/api/auth/login", json={"email": "g@d.com", "password": "pw"})
    assert guardian.post("/api/guardian/redeem", json={"code": "000000"}).status_code == 400
