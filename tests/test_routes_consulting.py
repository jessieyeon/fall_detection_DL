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
    auth.create_user(conn, "s@d.com", "pw", "admin", "관리자")
    auth.create_user(conn, "g@d.com", "pw", "admin", "관리자2")
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


def test_other_admin_cannot_read_report(env):
    """리포트는 만든 사람만 본다. 다른 관리자 계정으로는 못 읽는다."""
    owner = _login(env, "s@d.com")
    rid = owner.post("/api/consulting/analyze",
                     files={"file": ("c.mp4", b"x", "video/mp4")}).json()["job_id"]
    rid = owner.get(f"/api/consulting/status/{rid}").json()["report_id"]

    other = _login(env, "g@d.com")
    assert other.get(f"/api/consulting/report/{rid}").status_code == 403
    assert other.get("/api/consulting/reports").json() == []


def test_analyze_requires_login(env):
    from fastapi.testclient import TestClient
    r = TestClient(env).post("/api/consulting/analyze",
                             files={"file": ("c.mp4", b"x", "video/mp4")})
    assert r.status_code == 401


def test_cache_hit_skips_analysis(env, monkeypatch, tmp_path):
    """체험용 샘플이면 분석을 건너뛰고 즉시 리포트가 나와야 한다."""
    import os
    from webservice import routes_consulting as rc

    image = os.path.join(tmp_path, "cached.png")
    with open(image, "wb") as f:
        f.write(b"fake-png")

    called = []
    monkeypatch.setattr(rc, "_analyze",
                        lambda p: called.append(p) or (_ for _ in ()).throw(
                            AssertionError("캐시가 있는데 분석을 돌렸다")))
    monkeypatch.setattr(rc, "_lookup_cache", lambda path: {
        "location": "세대 내부",
        "findings": {"summary": "미리 계산된 요약", "findings": [], "grid": [],
                     "evidence": "근거"},
        "image": image,
    })

    senior = _login(env, "s@d.com")
    r = senior.post("/api/consulting/analyze",
                    files={"file": ("unit.mp4", b"sample-bytes", "video/mp4")},
                    data={"location": "세대 내부"})
    assert r.status_code == 200

    # 폴링 없이 바로 done — 프런트 흐름은 그대로 쓰면서 대기가 0이 된다
    st = senior.get(f"/api/consulting/status/{r.json()['job_id']}").json()
    assert st["status"] == "done"

    report = senior.get(f"/api/consulting/report/{st['report_id']}").json()
    assert report["summary"] == "미리 계산된 요약"
    assert report["evidence"] == "근거"
    assert not called


def test_unknown_video_still_runs_real_analysis(env, monkeypatch):
    """캐시에 없는 영상은 지금까지처럼 실제 분석을 타야 한다."""
    from webservice import routes_consulting as rc
    monkeypatch.setattr(rc, "_lookup_cache", lambda path: None)

    senior = _login(env, "s@d.com")
    r = senior.post("/api/consulting/analyze",
                    files={"file": ("mine.mp4", b"unseen", "video/mp4")})
    st = senior.get(f"/api/consulting/status/{r.json()['job_id']}").json()
    assert st["status"] == "done" and st["report_id"] is not None


def test_busy_server_returns_503(env, monkeypatch):
    """대기열이 가득 차면 무한 대기가 아니라 명확한 거절이어야 한다."""
    from webservice.consulting import jobs
    from webservice import routes_consulting as rc
    monkeypatch.setattr(rc, "_lookup_cache", lambda path: None)

    def busy(job_id, fn):
        raise jobs.TooBusy("지금 분석 요청이 많아 처리할 수 없습니다.")
    monkeypatch.setattr("webservice.consulting.jobs.run_in_background", busy)

    senior = _login(env, "s@d.com")
    r = senior.post("/api/consulting/analyze",
                    files={"file": ("x.mp4", b"bytes", "video/mp4")})
    assert r.status_code == 503
    assert "분석 요청이 많아" in r.json()["detail"]


def test_safe_upload_path_strips_traversal():
    import os
    from webservice import routes_consulting as rc
    p = rc._safe_upload_path("../../../etc/passwd")
    # the resolved path must stay directly inside the uploads dir
    assert os.path.dirname(os.path.abspath(p)) == os.path.abspath(rc._UPLOAD_DIR)
    assert "etc" not in os.path.basename(p) or os.path.basename(p).endswith("passwd")
    assert ".." not in p.split(rc._UPLOAD_DIR)[-1]
