"""SQLite 연결과 스키마. ORM 없이 stdlib sqlite3 직접 사용.

역할 구조: 관리자(admin) 단일 역할이다. 어르신용 앱이 없으므로 어르신 계정과
보호자-어르신 페어링은 두지 않는다. 관리자가 입주민(residents)과 카메라(cameras)를
등록하고, 낙상 이벤트(fall_events)를 받는다.

주소 정책: 시설명·주소는 관리자 계정에 한 번만 둔다(users.facility_name/address).
입주민은 호실(room)을 기본으로 갖고, 119 신고 지원 화면은 '시설주소 + 호실'로
조합한다 — 같은 주소를 입주민 수만큼 반복 입력하게 만들지 않기 위해서다.
입주민 개별 주소(residents.address)는 예외 경로다: 시설 밖에 거주하는 어르신
(재가 서비스 등)을 위해 두며, 값이 있으면 신고 지원이 시설 주소 대신 이것을 쓴다.
"""

import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daon.db")

# 카메라 설치 공간. SQL CHECK 로 박지 않고 파이썬 상수로 둔다 — 공간 이름은
# 제품 서사에 따라 또 바뀔 수 있고, SQLite 는 CHECK 를 ALTER 로 못 고친다.
LOCATIONS = ("세대 내부", "공용 라운지", "복도")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    pw_hash TEXT NOT NULL,
    -- 단일 역할. 컬럼을 남겨두는 것은 향후 역할 분리 여지를 위한 것이고,
    -- 코드에는 role 분기가 없어야 한다.
    role TEXT NOT NULL DEFAULT 'admin' CHECK (role IN ('admin')),
    name TEXT NOT NULL DEFAULT '',
    facility_name TEXT NOT NULL DEFAULT '',
    -- 시설 주소. 119 신고 지원과 근처 병원 조회(routes_home)의 기준점이다.
    address TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS residents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    age INTEGER,
    room TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    -- 개별 주소(선택). 비어 있으면 시설 주소를 쓴다 — 위 '주소 정책' 참고.
    address TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cameras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER NOT NULL REFERENCES users(id),
    -- NULL 허용이 핵심이다. 세대 내부 카메라는 입주민이 특정되지만
    -- 공용 라운지·복도는 누가 지나갈지 모른다. 그때는 시설 주소로 신고한다.
    resident_id INTEGER REFERENCES residents(id),
    name TEXT NOT NULL,
    location TEXT NOT NULL,
    -- 파이프라인(main.py --device-key)이 자기를 식별하는 값.
    device_key TEXT UNIQUE NOT NULL,
    paired_at TEXT NOT NULL DEFAULT (datetime('now')),
    -- 온라인/오프라인은 컬럼으로 저장하지 않고 이 값에서 계산한다. 저장해두면
    -- 파이프라인이 죽었을 때 'online' 인 채로 굳어버린다.
    last_seen_at TEXT
);

CREATE TABLE IF NOT EXISTS fall_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id INTEGER NOT NULL REFERENCES cameras(id),
    -- 감지 시점의 입주민을 그대로 박아둔다. 나중에 카메라의 연결이 바뀌어도
    -- 과거 이벤트가 엉뚱한 사람을 가리키면 안 된다.
    resident_id INTEGER REFERENCES residents(id),
    risk_score REAL,
    tiles_json TEXT NOT NULL DEFAULT '[]',
    occurred_at TEXT NOT NULL DEFAULT (datetime('now')),
    acknowledged_at TEXT,
    -- 119 신고 지원 화면을 연 시각. '자동 신고'가 아니므로 발신 기록이 아니라
    -- 관리자가 신고 절차에 들어간 시각이다.
    reported_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_fall_events_occurred
    ON fall_events (occurred_at DESC);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    video_ref TEXT NOT NULL,
    heatmap_path TEXT NOT NULL,
    findings_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def connect(path=None):
    # 호출 시점에 DB_PATH를 읽는다 — 기본인자에 바인딩하면 테스트의
    # monkeypatch(webservice.db.DB_PATH 교체)가 먹히지 않는다.
    conn = sqlite3.connect(path if path is not None else DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path=None):
    conn = connect(path)
    try:
        conn.executescript(_SCHEMA)
        # CREATE TABLE IF NOT EXISTS 는 이미 있는 테이블에 새 컬럼을 더해주지
        # 않는다. 배포 볼륨의 기존 DB 가 죽지 않도록 여기서 채워 넣는다.
        cols = {r[1] for r in conn.execute("PRAGMA table_info(residents)")}
        if "address" not in cols:                      # 2026-08-09 추가
            conn.execute("ALTER TABLE residents "
                         "ADD COLUMN address TEXT NOT NULL DEFAULT ''")
        conn.commit()
    finally:
        conn.close()
