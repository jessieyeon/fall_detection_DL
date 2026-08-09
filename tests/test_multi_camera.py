"""카메라 여러 대가 서로를 덮어쓰지 않는지.

예전에는 프레임·일시정지 상태를 전역으로 하나씩만 들고 있어서, 파이프라인을
두 개 띄우면 나중 것이 앞의 것을 지웠다. 실버타운처럼 여러 공간을 동시에 보는
설치에서는 성립하지 않는다.
"""

import os

import pytest
from fastapi.testclient import TestClient

from webservice import live

TOKEN = {"X-Live-Token": "daon-live"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    dbfile = os.path.join(tmp_path, "t.db")
    monkeypatch.setattr("webservice.db.DB_PATH", dbfile)
    monkeypatch.setenv("DAON_DEMO_DEVICES", "")
    from webservice import cameras, routes_live, seed, app as app_module
    seed.seed_demo(dbfile)
    cameras.registry._seen.clear()
    routes_live.frames._frames.clear()
    routes_live.control._paused.clear()
    return app_module.app


def _post_frame(app, device, payload):
    return TestClient(app).post(
        "/api/live/frame", content=payload,
        headers={**TOKEN, "X-Device-Key": device, "Content-Type": "image/jpeg"})


# ── FrameStore ────────────────────────────────────────────────────────

def test_frames_are_kept_per_camera():
    store = live.FrameStore()
    store.put(b"lounge", "cam-a")
    store.put(b"hall", "cam-b")
    assert store.get("cam-a")[1] == b"lounge"
    assert store.get("cam-b")[1] == b"hall"
    assert sorted(store.devices()) == ["cam-a", "cam-b"]


def test_anonymous_pipeline_still_works():
    """기기키 없이 띄우던 기존 실행 방식."""
    store = live.FrameStore()
    store.put(b"only")
    assert store.get()[1] == b"only"


def test_two_cameras_do_not_overwrite_each_other(env):
    _post_frame(env, "daon-cam-302", b"\xff\xd8-302")
    _post_frame(env, "daon-cam-411", b"\xff\xd8-411")

    c = TestClient(env)
    assert c.get("/api/live/frame.jpg", params={"device": "daon-cam-302"}).content == b"\xff\xd8-302"
    assert c.get("/api/live/frame.jpg", params={"device": "daon-cam-411"}).content == b"\xff\xd8-411"


def test_status_lists_streaming_cameras(env):
    _post_frame(env, "daon-cam-302", b"x")
    _post_frame(env, "daon-cam-411", b"y")
    out = TestClient(env).get("/api/live/status").json()
    assert sorted(out["stream_devices"]) == ["daon-cam-302", "daon-cam-411"]


def test_frame_of_unknown_camera_is_404(env):
    _post_frame(env, "daon-cam-302", b"x")
    r = TestClient(env).get("/api/live/frame.jpg", params={"device": "daon-cam-411"})
    assert r.status_code == 404


# ── 일시정지 ──────────────────────────────────────────────────────────

def test_pausing_one_camera_leaves_the_others_running(env):
    admin = TestClient(env)
    from webservice import seed
    admin.post("/api/auth/login",
               json={"email": seed.ADMIN_EMAIL, "password": seed.ADMIN_PW})

    admin.post("/api/live/control", json={"paused": True, "device": "daon-cam-302"})

    def paused_for(dev):
        return TestClient(env).get(
            "/api/live/control", headers={**TOKEN, "X-Device-Key": dev}).json()["paused"]

    assert paused_for("daon-cam-302") is True
    assert paused_for("daon-cam-411") is False


def test_control_requires_login(env):
    r = TestClient(env).post("/api/live/control", json={"paused": True, "device": "x"})
    assert r.status_code == 401


# ── 이벤트 라우팅 ─────────────────────────────────────────────────────

def test_event_carries_device_key(env):
    c = TestClient(env)
    from webservice import seed
    c.post("/api/auth/login", json={"email": seed.ADMIN_EMAIL, "password": seed.ADMIN_PW})
    with c.websocket_connect("/ws/live") as ws:
        TestClient(env).post("/api/live/event", json={"type": "reset"},
                             headers={**TOKEN, "X-Device-Key": "daon-cam-302"})
        assert ws.receive_json() == {"type": "reset", "device": "daon-cam-302"}


def test_event_without_device_key_keeps_old_shape(env):
    """구버전 프런트가 붙어 있어도 깨지지 않아야 한다."""
    c = TestClient(env)
    from webservice import seed
    c.post("/api/auth/login", json={"email": seed.ADMIN_EMAIL, "password": seed.ADMIN_PW})
    with c.websocket_connect("/ws/live") as ws:
        TestClient(env).post("/api/live/event", json={"type": "reset"}, headers=TOKEN)
        assert ws.receive_json() == {"type": "reset"}
