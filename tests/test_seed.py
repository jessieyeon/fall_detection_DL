import os
from webservice import seed, db, auth


def test_seed_creates_admin_account(tmp_path):
    path = os.path.join(tmp_path, "t.db")
    db.init_db(path)
    seed.seed_demo(path)
    conn = db.connect(path)
    row = auth.authenticate(conn, seed.ADMIN_EMAIL, seed.ADMIN_PW)
    assert row is not None and row["role"] == "admin"
    conn.close()


def test_seed_leaves_facility_info_blank(tmp_path):
    """시설명·주소는 비어 있어야 한다 — 관람객이 직접 입력해 보는 것이 체험이다.

    시드값이 채워져 있으면 첫 화면부터 남의 시설처럼 보인다.
    """
    path = os.path.join(tmp_path, "t.db")
    db.init_db(path)
    seed.seed_demo(path)
    conn = db.connect(path)
    row = conn.execute("SELECT facility_name, address FROM users WHERE email = ?",
                       (seed.ADMIN_EMAIL,)).fetchone()
    conn.close()
    assert row["facility_name"] == "" and row["address"] == ""


def test_seed_does_not_overwrite_admin_edits(tmp_path):
    """서버는 재시작마다 seed 를 돌린다. 관리자가 입력한 시설 정보가
    재시작 때마다 시드값으로 되돌아가면 안 된다."""
    path = os.path.join(tmp_path, "t.db")
    db.init_db(path)
    seed.seed_demo(path)
    conn = db.connect(path)
    conn.execute("UPDATE users SET facility_name = '한울요양원', "
                 "address = '부산시 해운대구' WHERE email = ?", (seed.ADMIN_EMAIL,))
    conn.commit()
    conn.close()

    seed.seed_demo(path)                     # 재시작 시뮬레이션

    conn = db.connect(path)
    row = conn.execute("SELECT facility_name, address FROM users WHERE email = ?",
                       (seed.ADMIN_EMAIL,)).fetchone()
    conn.close()
    assert row["facility_name"] == "한울요양원"
    assert row["address"] == "부산시 해운대구"


def test_seed_keeps_sample_minimal(tmp_path):
    """표본은 흐름을 보여줄 최소한 — 입주민 1명(김순자), 카메라 1대(라운지)."""
    path = os.path.join(tmp_path, "t.db")
    db.init_db(path)
    seed.seed_demo(path)
    conn = db.connect(path)
    residents = [r["name"] for r in conn.execute("SELECT name FROM residents")]
    cams = [r["name"] for r in conn.execute("SELECT name FROM cameras")]
    conn.close()
    assert residents == ["김순자"]
    assert cams == ["1층 라운지"]


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
