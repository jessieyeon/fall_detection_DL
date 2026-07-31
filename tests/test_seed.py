import os
from webservice import seed, db, auth


def test_seed_creates_demo_accounts(tmp_path):
    path = os.path.join(tmp_path, "t.db")
    db.init_db(path)
    seed.seed_demo(path)
    conn = db.connect(path)
    assert auth.authenticate(conn, "senior@daon.com", "pw")["role"] == "senior"
    assert auth.authenticate(conn, "guardian@daon.com", "pw")["role"] == "guardian"
    conn.close()


def test_seed_is_idempotent(tmp_path):
    path = os.path.join(tmp_path, "t.db")
    db.init_db(path)
    seed.seed_demo(path)
    seed.seed_demo(path)                       # 두 번 실행해도 예외 없음
    conn = db.connect(path)
    n = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    assert n == 2
