import os
import pytest
from webservice import db, auth, pairing


def _setup(tmp_path):
    path = os.path.join(tmp_path, "t.db")
    db.init_db(path)
    conn = db.connect(path)
    sid = auth.create_user(conn, "s@d.com", "pw", "senior", "어르신")
    gid = auth.create_user(conn, "g@d.com", "pw", "guardian", "보호자")
    return conn, sid, gid


def test_generate_then_redeem_links(tmp_path):
    conn, sid, gid = _setup(tmp_path)
    code = pairing.generate_code(conn, sid)
    assert len(code) == 6 and code.isdigit()
    assert pairing.redeem_code(conn, code, gid) == sid
    linked = conn.execute(
        "SELECT 1 FROM guardian_links WHERE senior_id=? AND guardian_id=?",
        (sid, gid)).fetchone()
    assert linked is not None
    # 코드는 1회용 — 두 번째 사용 불가
    with pytest.raises(ValueError):
        pairing.redeem_code(conn, code, gid)


def test_invalid_code_raises(tmp_path):
    conn, sid, gid = _setup(tmp_path)
    with pytest.raises(ValueError):
        pairing.redeem_code(conn, "000000", gid)


def test_expired_code_raises(tmp_path):
    from datetime import datetime, timedelta
    conn, sid, gid = _setup(tmp_path)
    past = (datetime.utcnow() - timedelta(hours=1)).isoformat()
    conn.execute("INSERT INTO pairing_codes (code, senior_id, expires_at) VALUES (?, ?, ?)",
                 ("123456", sid, past))
    conn.commit()
    with pytest.raises(ValueError):
        pairing.redeem_code(conn, "123456", gid)
    assert conn.execute("SELECT 1 FROM pairing_codes WHERE code = '123456'").fetchone() is None


def test_regenerate_replaces_old_code(tmp_path):
    conn, sid, gid = _setup(tmp_path)
    old = pairing.generate_code(conn, sid)
    new = pairing.generate_code(conn, sid)
    n = conn.execute("SELECT COUNT(*) FROM pairing_codes WHERE senior_id=?",
                     (sid,)).fetchone()[0]
    assert n == 1                       # 기존 코드 교체됨
    if old != new:
        with pytest.raises(ValueError):
            pairing.redeem_code(conn, old, gid)
