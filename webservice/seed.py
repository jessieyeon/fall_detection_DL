"""시연용 데이터 시드. 멱등.

계정 하나(관리자)와, 시연 화면이 비어 보이지 않도록 입주민·카메라 표본을 넣는다.
카메라 중 하나(device_key='daon-cam-lounge-1')는 실제 파이프라인이 붙는 자리다 —
main.py 를 그 키로 띄우면 '나의 카메라' 목록에서 온라인으로 바뀐다.
"""

from webservice import auth, db

ADMIN_EMAIL = "admin@daon.com"
ADMIN_PW = "pw"

_FACILITY_NAME = "다온실버타운"
_FACILITY_ADDRESS = "서울특별시 서대문구 연세로 50"

# (이름, 나이, 호실, 연락처, 비고)
_RESIDENTS = [
    ("김순자", 82, "302호", "010-0000-0001", "보행 보조기 사용"),
    ("박영수", 78, "305호", "010-0000-0002", ""),
    ("이말순", 85, "411호", "010-0000-0003", "야간 화장실 출입 잦음"),
]

# (이름, 설치 공간, device_key, 연결할 입주민 이름 또는 None)
_CAMERAS = [
    ("302호 세대", "세대 내부", "daon-cam-302", "김순자"),
    ("411호 세대", "세대 내부", "daon-cam-411", "이말순"),
    ("1층 라운지", "공용 라운지", "daon-cam-lounge-1", None),
    ("3층 복도", "복도", "daon-cam-hall-3", None),
]


def seed_demo(path=db.DB_PATH):
    db.init_db(path)
    conn = db.connect(path)
    try:
        row = conn.execute("SELECT id FROM users WHERE email = ?",
                           (ADMIN_EMAIL,)).fetchone()
        if row is None:
            admin_id = auth.create_user(conn, ADMIN_EMAIL, ADMIN_PW, "admin", "김관리자")
        else:
            admin_id = row["id"]

        conn.execute(
            "UPDATE users SET facility_name = ?, address = ? WHERE id = ?",
            (_FACILITY_NAME, _FACILITY_ADDRESS, admin_id))

        resident_ids = {}
        for name, age, room, phone, note in _RESIDENTS:
            found = conn.execute(
                "SELECT id FROM residents WHERE admin_id = ? AND name = ? AND room = ?",
                (admin_id, name, room)).fetchone()
            if found is None:
                cur = conn.execute(
                    "INSERT INTO residents (admin_id, name, age, room, phone, note) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (admin_id, name, age, room, phone, note))
                resident_ids[name] = cur.lastrowid
            else:
                resident_ids[name] = found["id"]

        for name, location, device_key, resident_name in _CAMERAS:
            exists = conn.execute(
                "SELECT 1 FROM cameras WHERE device_key = ?", (device_key,)).fetchone()
            if exists is None:
                conn.execute(
                    "INSERT INTO cameras (admin_id, resident_id, name, location, device_key) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (admin_id, resident_ids.get(resident_name), name, location, device_key))

        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    seed_demo()
    print(f"시연 데이터 준비 완료: {ADMIN_EMAIL} (비번 {ADMIN_PW})")
    print(f"  입주민 {len(_RESIDENTS)}명 · 카메라 {len(_CAMERAS)}대")
