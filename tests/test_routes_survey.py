import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    dbfile = os.path.join(tmp_path, "t.db")
    monkeypatch.setattr("webservice.db.DB_PATH", dbfile)
    from webservice import db, auth, app as app_module
    db.init_db(dbfile)
    conn = db.connect(dbfile)
    auth.create_user(conn, "senior@daon.com", "pw", "senior", "할머니")
    conn.close()
    c = TestClient(app_module.app)
    c.post("/api/auth/login", json={"email": "senior@daon.com", "password": "pw"})
    return c


def _answers(c):
    qs = c.get("/api/survey/questions").json()["questions"]
    return {q["id"]: 0 for q in qs}


def test_questions_public():
    # 로그인 없이도 문항은 받을 수 있다
    from fastapi.testclient import TestClient
    from webservice import app as app_module
    r = TestClient(app_module.app).get("/api/survey/questions")
    assert r.status_code == 200 and len(r.json()["questions"]) == 8


def test_submit_and_latest(client):
    r = client.post("/api/survey", json={"answers": _answers(client)})
    assert r.status_code == 200
    assert r.json() == {"score": 0, "risk_level": "낮음"}
    latest = client.get("/api/survey/latest").json()
    assert latest["risk_level"] == "낮음" and latest["score"] == 0


def test_latest_null_when_none(client):
    assert client.get("/api/survey/latest").json() is None


def test_submit_bad_answers_400(client):
    r = client.post("/api/survey", json={"answers": {"age": 99}})
    assert r.status_code == 400


def test_submit_requires_login(tmp_path, monkeypatch):
    dbfile = os.path.join(tmp_path, "t2.db")
    monkeypatch.setattr("webservice.db.DB_PATH", dbfile)
    from webservice import db, app as app_module
    db.init_db(dbfile)
    r = TestClient(app_module.app).post("/api/survey", json={"answers": {}})
    assert r.status_code == 401
