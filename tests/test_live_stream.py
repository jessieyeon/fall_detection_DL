"""카메라 영상 중계(MJPEG) 테스트.

스켈레톤만 보내면 브라우저에는 검은 배경 위의 선만 보인다. 영상까지 흘려야
'카메라가 연결됐다'는 것이 눈으로 확인된다.
"""

import os

import numpy as np
import pytest
from fastapi.testclient import TestClient

from webservice import live


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DAON_SKIP_WARMUP", "1")
    monkeypatch.setattr("webservice.db.DB_PATH", os.path.join(tmp_path, "t.db"))
    from webservice import app as app_module
    from webservice import routes_live
    routes_live.frames = live.FrameStore()      # 테스트 간 격리
    routes_live.control = live.CameraControl()
    return TestClient(app_module.app)


@pytest.fixture
def logged_in(client, tmp_path):
    from webservice import auth, db
    db.init_db(db.DB_PATH)
    conn = db.connect()
    try:
        auth.create_user(conn, "u@d.com", "pw", "guardian", "보호자")
    finally:
        conn.close()
    client.post("/api/auth/login", json={"email": "u@d.com", "password": "pw"})
    return client


TOKEN = {"X-Live-Token": "daon-live"}
JPEG = b"\xff\xd8\xff\xe0" + b"fake-jpeg-body" + b"\xff\xd9"


# --------------------------------------------------------------------------
# FrameStore
# --------------------------------------------------------------------------

def test_frame_store_keeps_only_latest():
    """실시간 화면에서 밀린 프레임은 쓸모없다 — 최신 한 장만 유지한다."""
    store = live.FrameStore()
    store.put(b"first")
    store.put(b"second")
    seq, jpeg = store.get()
    assert jpeg == b"second" and seq == 2


def test_frame_store_starts_empty():
    seq, jpeg = live.FrameStore().get()
    assert jpeg is None and seq == 0


def test_sequence_lets_consumer_detect_new_frames():
    """같은 그림을 반복 전송하지 않으려면 새 프레임인지 구분할 수 있어야 한다."""
    store = live.FrameStore()
    store.put(b"a")
    first = store.seq
    store.put(b"a")                     # 내용이 같아도 새 프레임이다
    assert store.seq != first


# --------------------------------------------------------------------------
# 인제스트
# --------------------------------------------------------------------------

def test_frame_ingest_requires_token(client):
    r = client.post("/api/live/frame", content=JPEG,
                    headers={"X-Live-Token": "wrong"})
    assert r.status_code == 401


def test_frame_ingest_and_fetch(client):
    assert client.post("/api/live/frame", content=JPEG, headers=TOKEN).status_code == 200
    r = client.get("/api/live/frame.jpg")
    assert r.status_code == 200
    assert r.content == JPEG
    assert r.headers["content-type"] == "image/jpeg"
    assert r.headers["cache-control"] == "no-store"


def test_empty_frame_rejected(client):
    assert client.post("/api/live/frame", content=b"", headers=TOKEN).status_code == 400


def test_oversized_frame_rejected(client):
    from webservice import routes_live
    big = b"x" * (routes_live.MAX_FRAME_BYTES + 1)
    assert client.post("/api/live/frame", content=big, headers=TOKEN).status_code == 413


def test_fetch_before_any_frame_is_404(client):
    assert client.get("/api/live/frame.jpg").status_code == 404


def test_status_reports_frame_count(client):
    assert client.get("/api/live/status").json()["frames"] == 0
    client.post("/api/live/frame", content=JPEG, headers=TOKEN)
    client.post("/api/live/frame", content=JPEG, headers=TOKEN)
    assert client.get("/api/live/status").json()["frames"] == 2


# --------------------------------------------------------------------------
# 카메라 연결 끊기/잇기 제어
# --------------------------------------------------------------------------

def test_control_starts_connected(client):
    assert client.get("/api/live/control", headers=TOKEN).json()["paused"] is False
    assert client.get("/api/live/status").json()["paused"] is False


def test_browser_can_pause_and_resume(logged_in):
    assert logged_in.post("/api/live/control", json={"paused": True}).json()["paused"] is True
    # 파이프라인이 가져가는 지점에도 반영돼야 실제로 카메라가 끊긴다
    assert logged_in.get("/api/live/control", headers=TOKEN).json()["paused"] is True
    assert logged_in.get("/api/live/status").json()["paused"] is True

    assert logged_in.post("/api/live/control", json={"paused": False}).json()["paused"] is False
    assert logged_in.get("/api/live/control", headers=TOKEN).json()["paused"] is False


def test_anonymous_cannot_control_camera(client):
    """남의 집 카메라를 로그인 없이 끄고 켜면 안 된다."""
    assert client.post("/api/live/control", json={"paused": True}).status_code == 401
    assert client.get("/api/live/control", headers=TOKEN).json()["paused"] is False


def test_pipeline_control_read_requires_token(client):
    assert client.get("/api/live/control",
                      headers={"X-Live-Token": "wrong"}).status_code == 401


# --------------------------------------------------------------------------
# LiveBridge — 프레임 축소·전송률 제한
# --------------------------------------------------------------------------

class FakeClient:
    def __init__(self, paused=False):
        self.posts = []
        self.gets = []
        self._paused = paused

    def get(self, url, **kw):
        self.gets.append(url)
        outer = self

        class R:
            status_code = 200

            @staticmethod
            def json():
                return {"paused": outer._paused}
        return R()

    def post(self, url, **kw):
        self.posts.append((url, kw))

        class R:
            status_code = 200
        return R()

    def close(self):
        pass


def _bridge():
    from webservice.live_bridge import LiveBridge
    fake = FakeClient()
    return LiveBridge("http://localhost:8000", client=fake), fake


def test_push_frame_downscales_large_images():
    """1080p 원본을 그대로 보내면 대역폭을 크게 먹는다. 판정은 이미 끝난 뒤라
    화질을 낮춰도 결과에 영향이 없다."""
    import cv2
    bridge, fake = _bridge()
    bridge.push_frame(np.zeros((1080, 1920, 3), dtype=np.uint8))

    assert len(fake.posts) == 1
    url, kw = fake.posts[0]
    assert url.endswith("/api/live/frame")
    assert kw["headers"]["Content-Type"] == "image/jpeg"

    decoded = cv2.imdecode(np.frombuffer(kw["content"], np.uint8), cv2.IMREAD_COLOR)
    assert decoded.shape[1] == bridge.frame_width      # 긴 변이 줄어들었다
    assert decoded.shape[0] == 270                     # 16:9 비율 유지


def test_push_frame_is_rate_limited():
    """포즈보다 훨씬 무거우므로 프레임률을 따로 제한한다."""
    bridge, fake = _bridge()
    small = np.zeros((120, 160, 3), dtype=np.uint8)
    for _ in range(5):
        bridge.push_frame(small)
    assert len(fake.posts) == 1, "제한 없이 매 프레임 전송했다"


def test_should_pause_reflects_server():
    from webservice.live_bridge import LiveBridge
    fake = FakeClient(paused=True)
    bridge = LiveBridge("http://localhost:8000", client=fake)
    assert bridge.should_pause() is True
    assert any("/api/live/control" in u for u in fake.gets)


def test_should_pause_is_rate_limited():
    """매 프레임 물어보면 초당 수십 번 요청이 날아간다."""
    from webservice.live_bridge import LiveBridge
    fake = FakeClient(paused=False)
    bridge = LiveBridge("http://localhost:8000", client=fake)
    for _ in range(10):
        bridge.should_pause()
    control_calls = [u for u in fake.gets if "/api/live/control" in u]
    assert len(control_calls) == 1, f"{len(control_calls)}번 조회했다"


def test_should_pause_keeps_last_state_when_server_unreachable():
    """네트워크가 잠깐 끊겼다고 카메라가 제멋대로 켜지면 안 된다."""
    from webservice.live_bridge import LiveBridge
    fake = FakeClient(paused=True)
    bridge = LiveBridge("http://localhost:8000", client=fake)
    assert bridge.should_pause() is True

    def boom(*a, **k):
        raise RuntimeError("network down")
    fake.get = boom
    bridge._last_control = 0        # 제한을 풀어 즉시 재조회하게 한다
    assert bridge.should_pause() is True


def test_push_frame_never_raises():
    """중계 실패가 감지 파이프라인을 죽이면 안 된다."""
    from webservice.live_bridge import LiveBridge

    class Boom:
        def get(self, url):
            raise RuntimeError("down")

        def post(self, *a, **kw):
            raise RuntimeError("down")

        def close(self):
            pass

    bridge = LiveBridge("http://localhost:8000", client=Boom())
    bridge.push_frame(np.zeros((60, 80, 3), dtype=np.uint8))   # 예외가 새면 실패
