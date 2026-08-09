import os
from webservice import seed, db, auth


def test_seed_creates_admin_account(tmp_path):
    path = os.path.join(tmp_path, "t.db")
    db.init_db(path)
    seed.seed_demo(path)
    conn = db.connect(path)
    row = auth.authenticate(conn, seed.ADMIN_EMAIL, seed.ADMIN_PW)
    assert row is not None and row["role"] == "admin"
    assert row["facility_name"] and row["address"]      # 신고 지원이 쓸 값
    conn.close()


def test_seed_creates_residents_and_cameras(tmp_path):
    path = os.path.join(tmp_path, "t.db")
    db.init_db(path)
    seed.seed_demo(path)
    conn = db.connect(path)
    assert conn.execute("SELECT COUNT(*) FROM residents").fetchone()[0] == len(seed._RESIDENTS)
    assert conn.execute("SELECT COUNT(*) FROM cameras").fetchone()[0] == len(seed._CAMERAS)
    conn.close()


def test_camera_locations_are_known(tmp_path):
    """카메라 설치 공간은 db.LOCATIONS 안의 값이어야 한다."""
    path = os.path.join(tmp_path, "t.db")
    db.init_db(path)
    seed.seed_demo(path)
    conn = db.connect(path)
    used = {r["location"] for r in conn.execute("SELECT location FROM cameras")}
    conn.close()
    assert used <= set(db.LOCATIONS)


def test_common_area_cameras_have_no_resident(tmp_path):
    """공용 라운지·복도 카메라는 입주민이 비어 있어야 한다.

    비워둘 수 있다는 것이 스키마 설계의 핵심이라(공용공간은 누가 지나갈지 모른다)
    시드가 실수로 채우면 그 전제가 무너진다.
    """
    path = os.path.join(tmp_path, "t.db")
    db.init_db(path)
    seed.seed_demo(path)
    conn = db.connect(path)
    rows = conn.execute(
        "SELECT location, resident_id FROM cameras WHERE location != '세대 내부'"
    ).fetchall()
    conn.close()
    assert rows and all(r["resident_id"] is None for r in rows)


def test_seed_is_idempotent(tmp_path):
    path = os.path.join(tmp_path, "t.db")
    db.init_db(path)
    seed.seed_demo(path)
    seed.seed_demo(path)                       # 두 번 실행해도 예외 없음
    conn = db.connect(path)
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("users", "residents", "cameras")}
    conn.close()
    assert counts == {"users": 1,
                      "residents": len(seed._RESIDENTS),
                      "cameras": len(seed._CAMERAS)}
