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

# 영속 데이터(DB·업로드·리포트 이미지)가 사는 곳.
#
# **왜 환경변수로 뺐나.** 예전에는 이 파일 옆(=webservice/)에 daon.db 를 두었다.
# 재배포하면 컨테이너 파일시스템이 새로 만들어져 전부 날아가므로 영구 볼륨을
# 붙여야 하는데, webservice/ 에는 **코드가 같이 들어 있다** — app.py,
# routes_*.py, consulting/*.py, frontend/dist 가 전부 여기다. 이 경로에 볼륨을
# 마운트하면 빈 볼륨이 그 위를 덮어써 코드가 통째로 가려지고, 서버는
# `ModuleNotFoundError: webservice.app` 로 기동조차 못 한다. (Railway 볼륨은
# 도커의 named volume 과 달리 이미지의 기존 내용을 볼륨으로 복사해주지 않는다.)
#
# 그래서 데이터만 따로 뺄 수 있게 했다. 볼륨은 코드가 없는 경로(/app/data)에
# 붙이고 DAON_DATA_DIR 로 그 경로를 가리킨다.
#
# 기본값은 예전과 같은 위치다 — 환경변수를 안 넣으면 동작이 하나도 안 바뀐다.
DATA_DIR = (os.environ.get("DAON_DATA_DIR")
            or os.path.dirname(os.path.abspath(__file__)))

DB_PATH = os.path.join(DATA_DIR, "daon.db")

# 볼륨이 갓 붙은 첫 기동에는 이 디렉터리가 비어 있을 수 있다. 없으면
# sqlite3.connect 가 'unable to open database file' 로 죽는데, 메시지만 봐서는
# 권한 문제인지 경로 문제인지 알 수 없어 디버깅이 오래 걸린다.
try:
    os.makedirs(DATA_DIR, exist_ok=True)
except OSError as _exc:               # 읽기전용 마운트 등 — 여기서 서버를 죽이진 않는다
    print(f"[db] 데이터 디렉터리를 만들지 못했습니다 ({DATA_DIR}): {_exc}")

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
    -- 상세 주소(동·호수·층 등). 우편번호 검색은 도로명까지만 주므로 나머지는
    -- 손으로 받아야 한다. address 에 이어 붙이지 않고 따로 두는 이유: 붙여서
    -- 저장하면 나중에 수정 화면에서 어디까지가 검색 결과였는지 되돌릴 수 없다.
    address_detail TEXT NOT NULL DEFAULT '',
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
        if "address_detail" not in cols:               # 2026-08-11 추가
            conn.execute("ALTER TABLE residents "
                         "ADD COLUMN address_detail TEXT NOT NULL DEFAULT ''")
        conn.commit()
    finally:
        conn.close()
