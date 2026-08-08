"""'내 카메라 체험'(/ws/live/self) — 판정 세션과 라우트.

실제 모델(joblib/pandas/sklearn)은 최소 테스트 환경에 없으므로, 스코어러를
주입 가능한 가짜로 바꿔 판정 흐름(streak → fall → reset)과 라우트 동작
(인증·수용 한도·가용성)을 검증한다. 특징 계산은 순수 수학이라 그대로 검증한다.
"""

import math

import pytest

from webservice import live_self
from webservice.live_self import SelfSession, SessionLimiter


class FakeScorer:
    """위험 확률을 미리 정해둔 대로 돌려주는 스코어러."""

    def __init__(self, seq=()):
        self.seq = list(seq)
        self.calls = 0
        self.resets = 0

    def update(self, *a, **k):
        self.calls += 1
        return self.seq.pop(0) if self.seq else 0.0

    def reset(self):
        self.resets += 1


TH = {"prob_threshold": 0.5, "persistence": 3,
      "tau_R": 0.5, "tau_R_strict": 0.8, "tau_lean": 0.35, "window": 5}

BUNDLE = {"version": 4}


def _lm(cy=0.5, tilt_x=0.0, spread=0.2):
    """어깨(11,12)·엉덩이(23,24)를 중심 cy 에 배치한 33개 랜드마크."""
    pts = [[0.5, cy, 0.0] for _ in range(33)]
    pts[11] = [0.4, cy - spread, 0.0]
    pts[12] = [0.6, cy - spread, 0.0]
    pts[23] = [0.4 + tilt_x, cy + spread, 0.0]
    pts[24] = [0.6 + tilt_x, cy + spread, 0.0]
    return pts


def _msg(t, lm, w=640, h=480):
    return {"t": t, "w": w, "h": h, "lm": lm, "wlm": None}


def _session(seq):
    return SelfSession(BUNDLE, thresholds=TH, scorer=FakeScorer(seq)), None


# --- 특징 계산 ---

def test_tilt_zero_when_upright():
    s = SelfSession(BUNDLE, thresholds=TH, scorer=FakeScorer())
    vy, vx, tilt, *_ = s._features(_lm(), None, 640, 480, 0.0)
    assert tilt == pytest.approx(0.0, abs=1e-3)
    assert vy == 0.0 and vx == 0.0


def test_tilt_45deg_when_hip_shifted():
    s = SelfSession(BUNDLE, thresholds=TH, scorer=FakeScorer())
    # 화면비 반영: dx*w == dy*h 가 되도록 이동량을 잡으면 45도
    spread = 0.2
    dx_norm = spread * 2 * 480 / 640          # dy = 0.4*480px → dx = 192px/640
    lm = _lm(tilt_x=dx_norm)
    assert s._features(lm, None, 640, 480, 0.0).tilt == pytest.approx(45.0, abs=0.5)


def test_vertical_velocity_from_descent():
    s = SelfSession(BUNDLE, thresholds=TH, scorer=FakeScorer())
    s._features(_lm(cy=0.4), None, 640, 480, 0.0)
    vy, *_ = s._features(_lm(cy=0.6), None, 640, 480, 0.1)
    # 정규화 0.2 하강 / 0.1초 = 2.0 (스무딩 창에 값이 하나라 그대로)
    assert vy == pytest.approx(2.0, abs=1e-6)


def test_tilt3d_from_world_landmarks():
    s = SelfSession(BUNDLE, thresholds=TH, scorer=FakeScorer())
    wlm = [[0.0, 0.0, 0.0]] * 33
    wlm = [list(p) for p in wlm]
    wlm[11] = [-0.2, -0.3, 0.0]; wlm[12] = [0.2, -0.3, 0.0]
    wlm[23] = [-0.2, 0.3, 0.3];  wlm[24] = [0.2, 0.3, 0.3]   # 깊이 방향 기울기
    tilt3d = s._features(_lm(), wlm, 640, 480, 0.0).tilt3d
    assert tilt3d == pytest.approx(math.degrees(math.atan2(0.3, 0.6)), abs=0.5)


# --- 판정 흐름 ---

def test_fall_fires_after_persistence():
    s, _ = _session([0.9] * 10)
    fired = []
    for i in range(4):
        # 하강 이동을 줘서 방향이 잡히게 한다
        for e in s.process(_msg(i * 0.1, _lm(cy=0.3 + i * 0.1))):
            fired.append(e)
    types = [e["type"] for e in fired]
    assert "fall" in types
    fall = next(e for e in fired if e["type"] == "fall")
    assert len(fall["tiles"]) == 1            # 배터리 규칙: 한 번에 1장
    assert fall["rows"] == 2 and fall["cols"] == 2


def test_no_fall_below_threshold():
    s, _ = _session([0.3] * 10)
    events = []
    for i in range(6):
        events += s.process(_msg(i * 0.1, _lm(cy=0.3 + i * 0.05)))
    assert all(e["type"] != "fall" for e in events)
    assert all(e["prog"][0] == 0 for e in events if e["type"] == "self")


def test_streak_resets_on_safe_frame():
    s, _ = _session([0.9, 0.9, 0.2, 0.9, 0.9])
    progs = []
    for i in range(5):
        for e in s.process(_msg(i * 0.1, _lm(cy=0.3 + i * 0.05))):
            if e["type"] == "self":
                progs.append(e["prog"][0])
    assert progs == [1, 2, 0, 1, 2]           # 끊기면 0부터 다시


def test_cooldown_blocks_refire():
    s, _ = _session([0.9] * 40)
    falls = 0
    for i in range(20):                        # 2.0초 — 쿨다운 3초 안
        falls += sum(1 for e in s.process(_msg(i * 0.1, _lm(cy=0.2 + i * 0.03)))
                     if e["type"] == "fall")
    assert falls == 1


def test_reset_sent_after_delay():
    s, _ = _session([0.9] * 40)
    events = []
    for i in range(40):                        # 4.0초 — RESET_DELAY(2초) 초과
        events += s.process(_msg(i * 0.1, _lm(cy=0.2 + i * 0.01)))
    types = [e["type"] for e in events]
    assert "reset" in types
    assert types.index("reset") > types.index("fall")


def test_pose_loss_resets_history():
    scorer = FakeScorer([0.9] * 10)
    s = SelfSession(BUNDLE, thresholds=TH, scorer=scorer)
    s.process(_msg(0.0, _lm()))
    s.process(_msg(0.1, None))                 # 사람 사라짐
    assert scorer.resets >= 1
    assert s._streak == 0


def test_flood_frames_dropped():
    scorer = FakeScorer([0.9] * 100)
    s = SelfSession(BUNDLE, thresholds=TH, scorer=scorer)
    for i in range(100):
        s.process(_msg(i * 0.001, _lm()))      # 1000fps 폭주
    assert scorer.calls < 20                   # MAX_FPS(40) 로 걸러짐


# --- 수용 한도 ---

def test_limiter():
    lim = SessionLimiter(limit=2)
    assert lim.acquire() and lim.acquire()
    assert not lim.acquire()
    lim.release()
    assert lim.acquire()


# --- 라우트 ---

@pytest.fixture
def app(tmp_path, monkeypatch):
    import os
    dbfile = os.path.join(tmp_path, "t.db")
    monkeypatch.setattr("webservice.db.DB_PATH", dbfile)
    from webservice import db, auth, app as app_module
    db.init_db(dbfile)
    conn = db.connect(dbfile)
    auth.create_user(conn, "s@d.com", "pw", "senior", "어르신")
    conn.close()
    return app_module.app


def _fake_ready(monkeypatch):
    monkeypatch.setattr(live_self, "load_bundle", lambda: BUNDLE)
    monkeypatch.setattr(
        live_self, "SelfSession",
        lambda bundle, thresholds=None, scorer=None:
            SelfSession(bundle, thresholds=TH, scorer=FakeScorer()))


def test_ws_self_requires_login(app):
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/live/self") as ws:
            ws.receive_json()


def test_ws_self_unavailable_without_model(app, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(live_self, "load_bundle", lambda: None)
    client = TestClient(app)
    client.post("/api/auth/login", json={"email": "s@d.com", "password": "pw"})
    with client.websocket_connect("/ws/live/self") as ws:
        assert ws.receive_json() == {"type": "unavailable"}


def test_ws_self_ready_and_scoring(app, monkeypatch):
    from fastapi.testclient import TestClient
    _fake_ready(monkeypatch)
    client = TestClient(app)
    client.post("/api/auth/login", json={"email": "s@d.com", "password": "pw"})
    with client.websocket_connect("/ws/live/self") as ws:
        ready = ws.receive_json()
        assert ready["type"] == "ready" and ready["persistence"] == 3
        ws.send_json(_msg(0.0, _lm()))
        m = ws.receive_json()
        assert m["type"] == "self" and "risk" in m and "prog" in m


def test_ws_self_busy_when_full(app, monkeypatch):
    from fastapi.testclient import TestClient
    from webservice import routes_live
    _fake_ready(monkeypatch)
    monkeypatch.setattr(routes_live, "self_limiter", SessionLimiter(limit=1))
    client = TestClient(app)
    client.post("/api/auth/login", json={"email": "s@d.com", "password": "pw"})
    with client.websocket_connect("/ws/live/self") as ws1:
        assert ws1.receive_json()["type"] == "ready"
        with client.websocket_connect("/ws/live/self") as ws2:
            assert ws2.receive_json() == {"type": "busy"}


def test_available_endpoint(app, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(live_self, "load_bundle", lambda: None)
    client = TestClient(app)
    r = client.get("/api/live/self/available")
    assert r.status_code == 200
    assert r.json() == {"available": False, "slots": 0}
    monkeypatch.setattr(live_self, "load_bundle", lambda: BUNDLE)
    assert client.get("/api/live/self/available").json()["available"] is True
