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


def create_user(conn, email, password, role, name=""):
    try:
        cur = conn.execute(
            "INSERT INTO users (email, pw_hash, role, name) VALUES (?, ?, ?, ?)",
            (email, hash_password(password), role, name))
        conn.commit()
    except sqlite3.IntegrityError as exc:
        raise ValueError(f"이미 존재하는 이메일: {email}") from exc
    return cur.lastrowid


def authenticate(conn, email, password):
    row = conn.execute(
        "SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if row is None or not verify_password(password, row["pw_hash"]):
        return None
    return row
