"""비밀번호 해시와 사용자 인증. stdlib만 사용."""

import hashlib
import hmac
import os
import sqlite3

_ITERATIONS = 200_000


def hash_password(password):
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"pbkdf2${_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password, stored):
    try:
        _algo, iters, salt_hex, hash_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iters))
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(dk.hex(), hash_hex)


def create_user(conn, email, password, role="admin", name=""):
    try:
        cur = conn.execute(
            "INSERT INTO users (email, pw_hash, role, name) VALUES (?, ?, ?, ?)",
            (email, hash_password(password), role, name))
        conn.commit()
    except sqlite3.IntegrityError as exc:
        # UNIQUE 위반과 CHECK 위반을 구분한다. 둘 다 IntegrityError 로 오기 때문에
        # 뭉뚱그리면 역할값이 틀렸을 때 '이미 존재하는 이메일'이라는 엉뚱한 메시지가
        # 나온다 — 스키마를 바꿀 때 실제로 이것 때문에 한참 헤맸다.
        if "CHECK constraint failed" in str(exc):
            raise ValueError(f"허용되지 않는 role 값: {role!r}") from exc
        raise ValueError(f"이미 존재하는 이메일: {email}") from exc
    return cur.lastrowid


def authenticate(conn, email, password):
    row = conn.execute(
        "SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if row is None or not verify_password(password, row["pw_hash"]):
        return None
    return row
