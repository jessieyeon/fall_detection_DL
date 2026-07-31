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
    return TestClient(app_module.app)


def test_login_success_and_me(client):
    r = client.post("/api/auth/login",
                    json={"email": "senior@daon.com", "password": "pw"})
    assert r.status_code == 200
    assert r.json()["role"] == "senior"
    me = client.get("/api/auth/me")
    assert me.status_code == 200 and me.json()["email"] == "senior@daon.com"


def test_login_wrong_password(client):
    r = client.post("/api/auth/login",
                    json={"email": "senior@daon.com", "password": "nope"})
    assert r.status_code == 401


def test_me_requires_login(client):
    assert client.get("/api/auth/me").status_code == 401


def test_logout_clears_session(client):
    client.post("/api/auth/login",
                json={"email": "senior@daon.com", "password": "pw"})
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401
