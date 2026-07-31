"""6자리 보호자 페어링 코드 생성·사용. 1인 1활성코드, 코드 1회용."""

import secrets
from datetime import datetime, timedelta

CODE_TTL_HOURS = 24


def _now_iso():
    return datetime.utcnow().isoformat()


def generate_code(conn, senior_id):
    # 한 어르신당 활성 코드는 하나만 유지 — 기존 코드 제거 후 발급.
    conn.execute("DELETE FROM pairing_codes WHERE senior_id = ?", (senior_id,))
    # ponytail: 6자리 공간(1e6)에서 서로 다른 어르신 간 코드 충돌은 무시 가능한 확률.
    # 데모 규모에서 재시도 루프는 과설계라 단일 삽입만 한다.
    code = f"{secrets.randbelow(1000000):06d}"
    expires = (datetime.utcnow() + timedelta(hours=CODE_TTL_HOURS)).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO pairing_codes (code, senior_id, expires_at) "
        "VALUES (?, ?, ?)", (code, senior_id, expires))
    conn.commit()
    return code


def redeem_code(conn, code, guardian_id):
    row = conn.execute(
        "SELECT senior_id, expires_at FROM pairing_codes WHERE code = ?",
        (code,)).fetchone()
    if row is None:
        raise ValueError("유효하지 않은 코드입니다")
    if row["expires_at"] < _now_iso():
        conn.execute("DELETE FROM pairing_codes WHERE code = ?", (code,))
        conn.commit()
        raise ValueError("만료된 코드입니다")
    senior_id = row["senior_id"]
    if senior_id == guardian_id:
        raise ValueError("본인과는 매칭할 수 없습니다")
    conn.execute(
        "INSERT OR IGNORE INTO guardian_links (senior_id, guardian_id) "
        "VALUES (?, ?)", (senior_id, guardian_id))
    conn.execute("DELETE FROM pairing_codes WHERE code = ?", (code,))
    conn.commit()
    return senior_id
