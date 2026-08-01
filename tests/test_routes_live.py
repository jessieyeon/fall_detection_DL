import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app(tmp_path, monkeypatch):
    dbfile = os.path.join(tmp_path, "t.db")
    monkeypatch.setattr("webservice.db.DB_PATH", dbfile)
    from webservice import db, auth, app as app_module
    db.init_db(dbfile)
    conn = db.connect(dbfile)
    auth.create_user(conn, "s@d.com", "pw", "senior", "어르신")
    conn.close()
    return app_module.app


def test_ws_requires_login(app):
    client = TestClient(app)
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/live"):
            pass


def test_event_broadcasts_to_subscriber(app):
    client = TestClient(app)
    client.post("/api/auth/login", json={"email": "s@d.com", "password": "pw"})
    with client.websocket_connect("/ws/live") as ws:
        r = client.post("/api/live/event",
                        headers={"X-Live-Token": "daon-live"},
                        json={"type": "reset"})
        assert r.status_code == 200 and r.json()["delivered"] >= 1
        assert ws.receive_json() == {"type": "reset"}


def test_event_bad_token_401(app):
    client = TestClient(app)
    r = client.post("/api/live/event", headers={"X-Live-Token": "wrong"},
                    json={"type": "reset"})
    assert r.status_code == 401


def test_event_bad_type_400(app):
    client = TestClient(app)
    r = client.post("/api/live/event", headers={"X-Live-Token": "daon-live"},
                    json={"type": "bogus"})
    assert r.status_code == 400


def test_event_missing_fields_400(app):
    client = TestClient(app)
    r = client.post("/api/live/event", headers={"X-Live-Token": "daon-live"},
                    json={"type": "fall", "tiles": [1]})   # rows/cols missing
    assert r.status_code == 400
