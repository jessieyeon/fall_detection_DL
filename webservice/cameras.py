"""입주민·카메라 관리와 기기 탐색(페어링).

pairing.py(어르신-보호자 6자리 코드)를 대체한다. 어르신 앱이 없으므로 코드를
주고받을 상대가 없고, 대신 관리자가 '주변 카메라를 찾아' 등록하는 흐름이 된다.

탐색 방식: 블루투스처럼 보이지만 실제로는 **최근에 서버로 신호를 보낸 device_key**
목록이다. 파이프라인(main.py --device-key)이 이벤트나 프레임을 올릴 때마다
registry.announce() 가 불리고, 아직 DB 에 등록되지 않은 키가 '발견된 기기'로 뜬다.

온라인 여부는 저장하지 않고 last_seen_at 에서 계산한다. 상태를 컬럼에 박아두면
파이프라인이 죽었을 때 online 인 채로 굳어서, 화면이 거짓말을 하게 된다.
"""

import os
import time
from datetime import datetime, timedelta, timezone

# 이 시간 안에 신호가 있었으면 온라인으로 본다. 파이프라인은 프레임을 초당
# 여러 장 올리므로 30초는 넉넉하다.
ONLINE_WINDOW_SEC = 30.0

# 탐색 목록에서 기기가 사라지기까지의 시간. 온라인 판정보다 길게 둔다 —
# 잠깐 끊겼다고 목록에서 사라지면 등록하려던 것을 놓친다.
DISCOVERY_TTL_SEC = 120.0


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(dt):
    return dt.isoformat(timespec="seconds")


def _is_online(last_seen_at):
    if not last_seen_at:
        return False
    try:
        seen = datetime.fromisoformat(last_seen_at)
    except ValueError:
        return False
    return (_now() - seen) <= timedelta(seconds=ONLINE_WINDOW_SEC)


def _demo_devices():
    """시연용 가짜 발견 기기.

    부스에서 '카메라 추가'를 눌렀을 때 목록이 비어 있으면 기능이 고장 난 것처럼
    보인다. 실제 파이프라인은 보통 한 대만 띄우므로 나머지를 채운다.
    DAON_DEMO_DEVICES="" 로 끄면 진짜 신호만 뜬다.

    형식: "키:표시이름,키:표시이름"
    """
    raw = os.environ.get(
        "DAON_DEMO_DEVICES",
        "daon-cam-lounge-2:라운지 카메라 (미등록),"
        "daon-cam-hall-5:복도 카메라 (미등록)")
    out = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        key, _, label = chunk.partition(":")
        out.append((key.strip(), label.strip() or key.strip()))
    return out


class DiscoveryRegistry:
    """최근에 신호를 보낸 device_key 를 기억한다. 프로세스 메모리에만 있다.

    영속화하지 않는 것은 의도다 — '지금 주변에 있는 기기'라는 개념 자체가
    휘발성이고, 서버가 재시작하면 다시 모아야 맞다.
    """

    def __init__(self, ttl=DISCOVERY_TTL_SEC):
        self._ttl = ttl
        self._seen = {}          # device_key -> monotonic 시각

    def announce(self, device_key):
        # device_key 는 HTTP 헤더(X-Device-Key)로 실려 오므로 ASCII 여야 한다.
        # 한글 키를 쓰면 파이프라인 쪽에서 요청 자체가 만들어지지 않는다.
        if not device_key:
            return
        self._seen[device_key] = time.monotonic()

    def active_keys(self):
        cutoff = time.monotonic() - self._ttl
        self._seen = {k: t for k, t in self._seen.items() if t >= cutoff}
        return set(self._seen)


registry = DiscoveryRegistry()


# ── 입주민 ────────────────────────────────────────────────────────────

_RESIDENT_FIELDS = ("name", "age", "room", "phone", "note", "address",
                    "address_detail")


def list_residents(conn, admin_id):
    rows = conn.execute(
        "SELECT id, name, age, room, phone, note, address, address_detail "
        "FROM residents WHERE admin_id = ? ORDER BY room, name",
        (admin_id,)).fetchall()
    return [dict(r) for r in rows]


def create_resident(conn, admin_id, name, age=None, room="", phone="", note="",
                    address="", address_detail=""):
    name = (name or "").strip()
    if not name:
        raise ValueError("이름은 비워둘 수 없습니다")
    cur = conn.execute(
        "INSERT INTO residents "
        "(admin_id, name, age, room, phone, note, address, address_detail) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (admin_id, name, age, room.strip(), phone.strip(), note.strip(),
         (address or "").strip(), (address_detail or "").strip()))
    conn.commit()
    return cur.lastrowid


def update_resident(conn, admin_id, resident_id, **fields):
    sets, vals = [], []
    for key in _RESIDENT_FIELDS:
        if key in fields and fields[key] is not None:
            value = fields[key]
            if key == "name":
                value = str(value).strip()
                if not value:
                    raise ValueError("이름은 비워둘 수 없습니다")
            elif key != "age":
                value = str(value).strip()
            sets.append(f"{key} = ?")
            vals.append(value)
    if not sets:
        return False
    vals += [resident_id, admin_id]
    cur = conn.execute(
        f"UPDATE residents SET {', '.join(sets)} WHERE id = ? AND admin_id = ?", vals)
    conn.commit()
    return cur.rowcount > 0


def delete_resident(conn, admin_id, resident_id):
    # 카메라가 이 입주민을 가리키고 있으면 연결만 끊는다. 카메라까지 지우면
    # 물리적으로 벽에 붙어 있는 장비가 화면에서 사라져 버린다.
    conn.execute(
        "UPDATE cameras SET resident_id = NULL "
        "WHERE resident_id = ? AND admin_id = ?", (resident_id, admin_id))
    cur = conn.execute("DELETE FROM residents WHERE id = ? AND admin_id = ?",
                       (resident_id, admin_id))
    conn.commit()
    return cur.rowcount > 0


# ── 카메라 ────────────────────────────────────────────────────────────

def list_cameras(conn, admin_id):
    rows = conn.execute(
        "SELECT c.id, c.name, c.location, c.device_key, c.paired_at, c.last_seen_at, "
        "       c.resident_id, r.name AS resident_name, r.room AS resident_room "
        "FROM cameras c LEFT JOIN residents r ON r.id = c.resident_id "
        "WHERE c.admin_id = ? ORDER BY c.location, c.name", (admin_id,)).fetchall()
    live = registry.active_keys()
    out = []
    for row in rows:
        item = dict(row)
        item["online"] = _is_online(row["last_seen_at"]) or row["device_key"] in live
        out.append(item)
    return out


def discoverable(conn, admin_id):
    """등록 가능한 기기 목록 — 신호는 왔는데 아직 DB 에 없는 device_key."""
    known = {r["device_key"] for r in conn.execute("SELECT device_key FROM cameras")}
    found = []
    for key in sorted(registry.active_keys()):
        if key not in known:
            found.append({"device_key": key, "label": key, "real": True})
    for key, label in _demo_devices():
        if key not in known and key not in registry.active_keys():
            found.append({"device_key": key, "label": label, "real": False})
    return found


def register_camera(conn, admin_id, device_key, name, location,
                    resident_id=None, locations=None):
    from webservice import db as _db
    device_key = (device_key or "").strip()
    name = (name or "").strip()
    if not device_key:
        raise ValueError("기기 식별자가 없습니다")
    if not name:
        raise ValueError("카메라 이름을 입력해 주세요")
    allowed = locations if locations is not None else _db.LOCATIONS
    if location not in allowed:
        raise ValueError(f"알 수 없는 설치 공간: {location!r}")
    if resident_id is not None:
        owned = conn.execute(
            "SELECT 1 FROM residents WHERE id = ? AND admin_id = ?",
            (resident_id, admin_id)).fetchone()
        if owned is None:
            raise ValueError("등록되지 않은 입주민입니다")
    exists = conn.execute("SELECT 1 FROM cameras WHERE device_key = ?",
                          (device_key,)).fetchone()
    if exists is not None:
        raise ValueError("이미 등록된 기기입니다")
    cur = conn.execute(
        "INSERT INTO cameras (admin_id, resident_id, name, location, device_key) "
        "VALUES (?, ?, ?, ?, ?)",
        (admin_id, resident_id, name, location, device_key))
    conn.commit()
    return cur.lastrowid


def update_camera(conn, admin_id, camera_id, name=None, location=None,
                  resident_id=..., locations=None):
    from webservice import db as _db
    sets, vals = [], []
    if name is not None:
        name = name.strip()
        if not name:
            raise ValueError("카메라 이름을 입력해 주세요")
        sets.append("name = ?"); vals.append(name)
    if location is not None:
        allowed = locations if locations is not None else _db.LOCATIONS
        if location not in allowed:
            raise ValueError(f"알 수 없는 설치 공간: {location!r}")
        sets.append("location = ?"); vals.append(location)
    # resident_id 는 None(연결 해제)과 '안 건드림'을 구분해야 해서 sentinel 을 쓴다.
    if resident_id is not ...:
        if resident_id is not None:
            owned = conn.execute(
                "SELECT 1 FROM residents WHERE id = ? AND admin_id = ?",
                (resident_id, admin_id)).fetchone()
            if owned is None:
                raise ValueError("등록되지 않은 입주민입니다")
        sets.append("resident_id = ?"); vals.append(resident_id)
    if not sets:
        return False
    vals += [camera_id, admin_id]
    cur = conn.execute(
        f"UPDATE cameras SET {', '.join(sets)} WHERE id = ? AND admin_id = ?", vals)
    conn.commit()
    return cur.rowcount > 0


def delete_camera(conn, admin_id, camera_id):
    cur = conn.execute("DELETE FROM cameras WHERE id = ? AND admin_id = ?",
                       (camera_id, admin_id))
    conn.commit()
    return cur.rowcount > 0


def touch(conn, device_key):
    """파이프라인 신호를 받았을 때 호출. 탐색 목록과 last_seen_at 을 갱신한다."""
    registry.announce(device_key)
    if not device_key:
        return
    conn.execute("UPDATE cameras SET last_seen_at = ? WHERE device_key = ?",
                 (_iso(_now()), device_key))
    conn.commit()


# ── 119 신고 지원 ─────────────────────────────────────────────────────

def dispatch_info(conn, camera_id):
    """신고에 필요한 정보를 한 덩어리로 만든다.

    자동 신고가 아니다. 관리자가 통화하면서 그대로 읽을 수 있는 문장을 만드는 것이
    목적이라, 주소는 조각으로도 주고 합친 문자열로도 준다.
    """
    row = conn.execute(
        "SELECT c.id, c.name AS camera_name, c.location, "
        "       u.facility_name, u.address, "
        "       r.id AS resident_id, r.name AS resident_name, r.age, r.room, "
        "       r.phone, r.address AS resident_address, "
        "       r.address_detail AS resident_address_detail "
        "FROM cameras c JOIN users u ON u.id = c.admin_id "
        "LEFT JOIN residents r ON r.id = c.resident_id "
        "WHERE c.id = ?", (camera_id,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    if d.get("resident_address"):
        # 개별 주소가 있는 어르신(시설 밖 거주)은 그 주소가 곧 출동지다.
        # 시설 주소를 섞으면 구급대가 엉뚱한 곳으로 간다.
        parts = [d["resident_address"]]
        # 상세 주소(동·호수)는 도로명 바로 뒤에 붙어야 읽어주기 좋다.
        if d.get("resident_address_detail"):
            parts.append(d["resident_address_detail"])
        elif d["room"]:
            # 상세 주소를 안 넣었으면 호실이라도 붙인다(예전 데이터 호환).
            parts.append(d["room"])
    else:
        parts = [p for p in (d["address"], d["facility_name"]) if p]
        if d["room"]:
            parts.append(d["room"])
        else:
            # 공용공간이면 호실이 없다. 어디인지는 설치 공간과 카메라 이름으로 좁힌다.
            parts.append(f"{d['location']} ({d['camera_name']})")
    d["dispatch_address"] = " ".join(parts)
    d["identified"] = d["resident_id"] is not None
    return d
