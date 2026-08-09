import os
from webservice import db


def test_init_db_creates_tables(tmp_path):
    path = os.path.join(tmp_path, "test.db")
    db.init_db(path)
    conn = db.connect(path)
    names = {row["name"] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert {"users", "residents", "cameras", "fall_events", "reports"} <= names
    # 어르신 계정 구조의 잔재가 되살아나지 않도록 못을 박아둔다.
    assert names.isdisjoint({"guardian_links", "pairing_codes", "surveys"})


def test_connect_enables_foreign_keys(tmp_path):
    path = os.path.join(tmp_path, "test.db")
    db.init_db(path)
    conn = db.connect(path)
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    conn.close()
