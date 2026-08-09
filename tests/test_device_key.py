"""파이프라인이 자기를 밝히면 관리자 화면에 나타나는지 — 끝에서 끝까지."""

import os

import httpx
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def env(tmp_path, monkeypatch):
    dbfile = os.path.join(tmp_path, "t.db")
    monkeypatch.setattr("webservice.db.DB_PATH", dbfile)
    monkeypatch.setenv("DAON_DEMO_DEVICES", "")
    from webservice import cameras, seed, app as app_module
    seed.seed_demo(dbfile)
    cameras.registry._seen.clear()
    return app_module.app


def _admin(app):
    from webservice import seed
    c = TestClient(app)
    c.post("/api/auth/login",
           json={"email": seed.ADMIN_EMAIL, "password": seed.ADMIN_PW})
    return c


def test_registered_camera_goes_online_after_signal(env):
    admin = _admin(env)
    assert all(not c["online"] for c in admin.get("/api/admin/cameras").json())

    TestClient(env).post("/api/live/event",
                         json={"type": "reset"},
                         headers={"X-Live-Token": "daon-live",
                                  "X-Device-Key": "daon-cam-lounge-1"})

    cams = {c["device_key"]: c for c in admin.get("/api/admin/cameras").json()}
    assert cams["daon-cam-lounge-1"]["online"] is True

    # 신호 없는 카메라는 그대로 오프라인. 시드에는 한 대뿐이라 직접 만든다.
    admin.post("/api/admin/cameras",
               json={"device_key": "daon-cam-quiet", "name": "3층 복도",
                     "location": "복도"})
    cams = {c["device_key"]: c for c in admin.get("/api/admin/cameras").json()}
    assert cams["daon-cam-quiet"]["online"] is False


def test_unknown_device_shows_up_in_scan(env):
    admin = _admin(env)
    TestClient(env).post("/api/live/event",
                         json={"type": "reset"},
                         headers={"X-Live-Token": "daon-live",
                                  "X-Device-Key": "daon-cam-unseen-1"})

    found = {d["device_key"] for d in admin.get("/api/admin/cameras/scan").json()}
    assert found == {"daon-cam-unseen-1"}


def test_relay_without_device_key_still_works(env):
    """기존 실행 방식(--device-key 없이)이 그대로 돌아야 한다."""
    r = TestClient(env).post("/api/live/event", json={"type": "reset"},
                             headers={"X-Live-Token": "daon-live"})
    assert r.status_code == 200
    assert _admin(env).get("/api/admin/cameras/scan").json() == []


def test_bridge_sends_device_key_header():
    from webservice import live_bridge

    seen = {}

    def handler(request):
        seen[str(request.url).rsplit("/", 1)[-1]] = dict(request.headers)
        return httpx.Response(200, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    bridge = live_bridge.LiveBridge("http://x", client=client,
                                    device_key="daon-cam-lounge-1")
    bridge.push_reset()
    assert seen["event"]["x-device-key"] == "daon-cam-lounge-1"


def test_bridge_omits_header_when_no_key(monkeypatch):
    from webservice import live_bridge
    monkeypatch.delenv("DAON_DEVICE_KEY", raising=False)

    seen = {}

    def handler(request):
        seen.update(dict(request.headers))
        return httpx.Response(200, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    live_bridge.LiveBridge("http://x", client=client).push_reset()
    assert "x-device-key" not in seen
