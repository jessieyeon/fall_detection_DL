"""시연용 계정 시드. 멱등."""

from webservice import auth, db

_DEMO = [
    ("senior@daon.com", "pw", "senior", "김할머니"),
    ("guardian@daon.com", "pw", "guardian", "김보호자"),
]


def seed_demo(path=db.DB_PATH):
    db.init_db(path)
    conn = db.connect(path)
    try:
        for email, pw, role, name in _DEMO:
            exists = conn.execute(
                "SELECT 1 FROM users WHERE email = ?", (email,)).fetchone()
            if exists is None:
                auth.create_user(conn, email, pw, role, name)
        conn.execute(
            "UPDATE users SET address = ?, apartment_name = ? WHERE email = ?",
            ("서울특별시 서대문구 연세로 50", "다온아파트", "senior@daon.com"))
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    seed_demo()
    print("시연 계정 준비 완료: senior@daon.com / guardian@daon.com (둘 다 비번 pw)")
