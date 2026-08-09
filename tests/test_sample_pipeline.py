"""사전 계산 캐시의 실제 이음매 테스트.

기존 라우트 테스트는 `_lookup_cache` 를 통째로 monkeypatch 하므로, **매니페스트
파일을 실제로 읽는 경로는 한 번도 실행되지 않는다.** 그래서 `build_samples.py`
가 쓰는 형식과 `cache.lookup` 이 읽는 형식이 어긋나도 테스트는 전부 통과한다.
샘플 영상이 완성되는 날 그 어긋남을 처음 발견하면 늦다.

여기서는 스크립트가 만든 **진짜 매니페스트**를 놓고 업로드까지 태운다.
YOLO 만 대역으로 바꾸고, 해시 계산·매니페스트 입출력·라우트 조회는 실제 코드다.
"""

import json
import os

import numpy as np
import pytest
from fastapi.testclient import TestClient

VIDEO_BYTES = b"pretend-this-is-unit-mp4-content"


def _fake_analyze(video_path):
    """좌상단으로 이어지는 동선 하나를 가진 합성 결과."""
    pmap = np.zeros((40, 40), dtype=np.float32)
    pmap[0:14, 0:14] = 100.0
    first = np.zeros((40, 40, 3), dtype=np.uint8)
    segments = [[(3.0, 3.0), (6.0, 4.0), (9.0, 8.0), (10.0, 12.0)]]
    return pmap, first, segments


@pytest.fixture
def sample_dir(tmp_path, monkeypatch):
    """cache 모듈이 tmp 안의 samples/ 를 보도록 돌려놓는다."""
    from webservice.consulting import cache
    d = os.path.join(tmp_path, "samples")
    os.makedirs(d, exist_ok=True)
    monkeypatch.setattr(cache, "SAMPLE_DIR", d)
    monkeypatch.setattr(cache, "MANIFEST_PATH", os.path.join(d, "manifest.json"))
    return d


@pytest.fixture
def built(tmp_path, sample_dir, monkeypatch):
    """build_samples.py 를 실제로 돌려 매니페스트를 만든다 (YOLO 만 대역)."""
    import scripts.build_samples as bs
    from webservice.consulting import analyze as analyze_mod, cache, transcode

    monkeypatch.setattr(analyze_mod, "analyze_video", _fake_analyze)
    monkeypatch.setattr(transcode, "ensure_readable", lambda p: (p, False))

    video = os.path.join(tmp_path, "unit.mp4")
    with open(video, "wb") as f:
        f.write(VIDEO_BYTES)

    entry = bs.analyze_one("세대 내부", video)
    cache.save_manifest({cache.file_sha256(video): entry})
    return video


def test_build_writes_manifest_that_lookup_can_read(built, sample_dir):
    """스크립트가 쓴 것을 서버가 그대로 읽을 수 있어야 한다."""
    from webservice.consulting import cache

    hit = cache.lookup(built)
    assert hit is not None, "build_samples 가 쓴 매니페스트를 lookup 이 못 읽었다"
    assert hit["location"] == "세대 내부"
    assert hit["findings"]["summary"]
    # 매니페스트에는 상대 경로로 저장하고, 조회 시 절대 경로로 펴준다
    assert os.path.isabs(hit["image"]) and os.path.isfile(hit["image"])

    with open(os.path.join(sample_dir, "manifest.json"), encoding="utf-8") as f:
        raw = json.load(f)
    assert not os.path.isabs(next(iter(raw.values()))["image"])


def test_renamed_file_still_hits_cache(built, tmp_path):
    """관람객이 파일명을 바꿔 올려도 내용이 같으면 캐시가 걸려야 한다."""
    from webservice.consulting import cache

    copy = os.path.join(tmp_path, "내_영상.mp4")
    with open(copy, "wb") as f:
        f.write(VIDEO_BYTES)
    assert cache.lookup(copy) is not None


def test_rebuilt_video_misses_cache(built, tmp_path):
    """영상을 다시 만들면 해시가 바뀌므로 캐시가 안 걸려야 한다(재실행 필요 신호)."""
    from webservice.consulting import cache

    other = os.path.join(tmp_path, "unit_v2.mp4")
    with open(other, "wb") as f:
        f.write(VIDEO_BYTES + b"!")
    assert cache.lookup(other) is None


@pytest.fixture
def app(tmp_path, monkeypatch):
    dbfile = os.path.join(tmp_path, "t.db")
    monkeypatch.setattr("webservice.db.DB_PATH", dbfile)
    from webservice import auth, db, app as app_module
    db.init_db(dbfile)
    conn = db.connect(dbfile)
    auth.create_user(conn, "s@d.com", "pw", "admin", "관리자")
    conn.close()
    return app_module.app


def test_upload_of_sample_returns_precomputed_report(app, built, monkeypatch):
    """샘플 업로드는 분석 없이, 실제 매니페스트를 읽어 즉시 완료돼야 한다.

    `_lookup_cache` 를 가로채지 않는다 — 라우트가 cache 모듈을 실제로 부른다.
    """
    from webservice import routes_consulting as rc

    def must_not_run(path):
        raise AssertionError("캐시가 있는데 실제 분석을 돌렸다")
    monkeypatch.setattr(rc, "_analyze", must_not_run)

    c = TestClient(app)
    c.post("/api/auth/login", json={"email": "s@d.com", "password": "pw"})
    r = c.post("/api/consulting/analyze",
               files={"file": ("아무이름.mp4", VIDEO_BYTES, "video/mp4")},
               data={"location": "세대 내부"})
    assert r.status_code == 200

    st = c.get(f"/api/consulting/status/{r.json()['job_id']}").json()
    assert st["status"] == "done", "캐시 적중인데 폴링을 돌게 만들었다"

    report = c.get(f"/api/consulting/report/{st['report_id']}").json()
    assert report["location"] == "세대 내부"
    assert report["summary"]
    # 리포트 이미지가 실제로 서빙돼야 화면이 깨지지 않는다
    img = c.get(f"/api/consulting/report/{st['report_id']}/image")
    assert img.status_code == 200 and img.content


def test_upload_does_not_keep_a_second_copy_of_the_sample(app, built, tmp_path,
                                                          monkeypatch):
    """캐시 적중이면 업로드 원본을 남기지 않는다 — 전시 중 디스크가 샌다."""
    from webservice import routes_consulting as rc

    updir = os.path.join(tmp_path, "uploads")
    os.makedirs(updir, exist_ok=True)
    monkeypatch.setattr(rc, "_UPLOAD_DIR", updir)
    monkeypatch.setattr(rc, "_analyze",
                        lambda p: (_ for _ in ()).throw(AssertionError("분석함")))

    c = TestClient(app)
    c.post("/api/auth/login", json={"email": "s@d.com", "password": "pw"})
    c.post("/api/consulting/analyze",
           files={"file": ("unit.mp4", VIDEO_BYTES, "video/mp4")})
    assert os.listdir(updir) == []


def test_missing_samples_dir_falls_back_to_real_analysis(app, sample_dir, monkeypatch):
    """샘플을 아직 안 만들었어도 서비스는 평소대로 돌아야 한다.

    지금(영상 준비 전) 배포된 서버가 정확히 이 상태다.
    """
    from webservice import routes_consulting as rc
    from webservice.consulting import jobs

    ran = []

    def fake(path):
        ran.append(path)
        return (np.zeros((30, 30), dtype=np.float32),
                np.zeros((30, 30, 3), dtype=np.uint8), [])

    monkeypatch.setattr(rc, "_analyze", fake)
    monkeypatch.setattr(rc, "_ensure_readable", lambda p: (p, False))
    monkeypatch.setattr(jobs, "run_in_background",
                        lambda jid, fn: jobs._set(jid, status="done", report_id=fn()))

    c = TestClient(app)
    c.post("/api/auth/login", json={"email": "s@d.com", "password": "pw"})
    r = c.post("/api/consulting/analyze",
               files={"file": ("처음보는영상.mp4", b"never-seen", "video/mp4")})
    assert r.status_code == 200
    st = c.get(f"/api/consulting/status/{r.json()['job_id']}").json()
    assert st["status"] == "done" and ran
