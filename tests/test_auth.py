import os
import pytest
from webservice import auth, db


def _conn(tmp_path):
    path = os.path.join(tmp_path, "t.db")
    db.init_db(path)
    return db.connect(path)


def test_hash_roundtrip():
    h = auth.hash_password("hunter2")
    assert h != "hunter2"                 # 평문 저장 금지
    assert h.startswith("pbkdf2$")
    assert auth.verify_password("hunter2", h) is True
    assert auth.verify_password("wrong", h) is False


def test_hash_is_salted():
    assert auth.hash_password("same") != auth.hash_password("same")


def test_create_and_authenticate(tmp_path):
    conn = _conn(tmp_path)
    uid = auth.create_user(conn, "a@b.com", "pw", "senior", "할머니")
    assert isinstance(uid, int)
    row = auth.authenticate(conn, "a@b.com", "pw")
    assert row is not None and row["id"] == uid and row["role"] == "senior"
    assert auth.authenticate(conn, "a@b.com", "nope") is None
    assert auth.authenticate(conn, "no@b.com", "pw") is None


def test_duplicate_email_rejected(tmp_path):
    conn = _conn(tmp_path)
    auth.create_user(conn, "a@b.com", "pw", "senior")
    with pytest.raises(ValueError):
        auth.create_user(conn, "a@b.com", "pw2", "guardian")
