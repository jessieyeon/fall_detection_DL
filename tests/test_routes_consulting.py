import os
import time
import numpy as np
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

    # YOLO 우회: 좌상단이 뜨거운 합성 히트맵을 반환
    def fake_analyze(video_path):
        hm = np.zeros((30, 30), dtype=np.float32)
        hm[0:10, 0:10] = 100.0
        return hm, np.zeros((30, 30, 3), dtype=np.uint8)
    monkeypatch.setattr("webservice.routes_consulting._analyze", fake_analyze)

    # 업로드 바이트가 진짜 영상이 아니므로 ffmpeg 정규화도 우회한다.
    monkeypatch.setattr("webservice.routes_consulting._ensure_readable",
                        lambda path: (path, False))

    # 잡을 동기 실행해 테스트를 결정적으로
    def sync_run(job_id, fn):
        from webservice.consulting import jobs
        try:
            rid = fn()
            jobs._set(job_id, status="done", report_id=rid)
        except Exception as exc:
            jobs._set(job_id, status="error", error=str(exc))
    monkeypatch.setattr("webservice.consulting.jobs.run_in_background", sync_run)

    return app_module.app


def _login(app, email):
    c = TestClient(app)
    c.post("/api/auth/login", json={"email": email, "password": "pw"})
    return c


def test_analyze_creates_report(env):
    senior = _login(env, "s@d.com")
    r = senior.post("/api/consulting/analyze",
                    files={"file": ("clip.mp4", b"fake-bytes", "video/mp4")})
    assert r.status_code == 200
    job_id = r.json()["job_id"]

    st = senior.get(f"/api/consulting/status/{job_id}").json()
    assert st["status"] == "done"
    rid = st["report_id"]

    report = senior.get(f"/api/consulting/report/{rid}").json()
    assert report["findings"][0]["cell"] == [0, 0]
    assert report["summary"]

    img = senior.get(f"/api/consulting/report/{rid}/image")
    assert img.status_code == 200 and img.headers["content-type"].startswith("image")

    listing = senior.get("/api/consulting/reports").json()
    assert len(listing) == 1 and listing[0]["id"] == rid


def test_guardian_can_read_linked_senior_report(env):
    senior = _login(env, "s@d.com")
    code = senior.post("/api/guardian/code").json()["code"]
    rid = senior.post("/api/consulting/analyze",
                      files={"file": ("c.mp4", b"x", "video/mp4")}).json()["job_id"]
    rid = senior.get(f"/api/consulting/status/{rid}").json()["report_id"]

    guardian = _login(env, "g@d.com")
    guardian.post("/api/guardian/redeem", json={"code": code})
    assert guardian.get(f"/api/consulting/report/{rid}").status_code == 200
    assert len(guardian.get("/api/consulting/reports").json()) == 1


def test_unlinked_guardian_denied(env):
    senior = _login(env, "s@d.com")
    rid = senior.post("/api/consulting/analyze",
                      files={"file": ("c.mp4", b"x", "video/mp4")}).json()["job_id"]
    rid = senior.get(f"/api/consulting/status/{rid}").json()["report_id"]
    guardian = _login(env, "g@d.com")          # 연결 안 함
    assert guardian.get(f"/api/consulting/report/{rid}").status_code == 403


def test_analyze_requires_login(env):
    from fastapi.testclient import TestClient
    r = TestClient(env).post("/api/consulting/analyze",
                             files={"file": ("c.mp4", b"x", "video/mp4")})
    assert r.status_code == 401


def test_safe_upload_path_strips_traversal():
    import os
    from webservice import routes_consulting as rc
    p = rc._safe_upload_path("../../../etc/passwd")
    # the resolved path must stay directly inside the uploads dir
    assert os.path.dirname(os.path.abspath(p)) == os.path.abspath(rc._UPLOAD_DIR)
    assert "etc" not in os.path.basename(p) or os.path.basename(p).endswith("passwd")
    assert ".." not in p.split(rc._UPLOAD_DIR)[-1]
