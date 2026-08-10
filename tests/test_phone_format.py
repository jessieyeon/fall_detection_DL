"""연락처 형식 — 3-4-4 (010-1234-5678).

119 지원 화면에서 관리자가 그대로 읽어주는 값이라 형식이 섞이면 안 된다.
프런트가 입력 중에 하이픈을 넣어주지만, 서버도 같은 규칙으로 한 번 더 맞춘다
(저장 경로가 화면 하나뿐이라는 보장이 없다).
"""

import pytest
from fastapi.testclient import TestClient

from webservice import auth, cameras, db, seed
from webservice.app import app


# ── 정규화 규칙 ───────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("01012345678", "010-1234-5678"),        # 숫자만 붙여 넣은 경우
    ("010-1234-5678", "010-1234-5678"),      # 이미 맞는 값은 그대로
    ("010 1234 5678", "010-1234-5678"),      # 공백 구분
    ("010.1234.5678", "010-1234-5678"),
    ("  01012345678  ", "010-1234-5678"),    # 앞뒤 공백
    ("(010) 1234-5678", "010-1234-5678"),
])
def test_eleven_digits_become_3_4_4(raw, expected):
    assert cameras.normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", [
    "", "   ",
])
def test_blank_stays_blank(raw):
    assert cameras.normalize_phone(raw) == ""


def test_none_is_safe():
    assert cameras.normalize_phone(None) == ""


@pytest.mark.parametrize("raw", [
    "02-123-4567",        # 지역번호 대표전화
    "1588-0000",          # 대표번호
    "010-1234",           # 아직 덜 적은 값
])
def test_other_lengths_are_left_alone(raw):
    """11자리가 아니면 서버가 임의로 뭉개지 않는다.

    사용자가 넣은 정보를 소리 없이 바꾸는 것이 더 나쁘다. 3-4-4 강제는 입력
    화면에서 하고, 서버는 형식이 확실할 때만 손댄다.
    """
    assert cameras.normalize_phone(raw) == raw


# ── API 를 통해서도 같은 값이 남는지 ──────────────────────────────────

@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("DAON_SKIP_SEED", "1")
    db.init_db()
    conn = db.connect()
    try:
        auth.create_user(conn, seed.ADMIN_EMAIL, seed.ADMIN_PW, "admin", "김관리자")
    finally:
        conn.close()
    with TestClient(app) as c:
        c.post("/api/auth/login",
               json={"email": seed.ADMIN_EMAIL, "password": seed.ADMIN_PW})
        yield c


def test_create_stores_hyphenated(client):
    client.post("/api/admin/residents",
                json={"name": "김순자", "phone": "01012345678"})
    (row,) = client.get("/api/admin/residents").json()
    assert row["phone"] == "010-1234-5678"


def test_patch_stores_hyphenated(client):
    rid = client.post("/api/admin/residents",
                      json={"name": "김순자"}).json()["id"]
    client.patch(f"/api/admin/residents/{rid}", json={"phone": "01098765432"})
    (row,) = client.get("/api/admin/residents").json()
    assert row["phone"] == "010-9876-5432"


def test_phone_stays_optional(client):
    """연락처는 선택 항목이다 — 비워도 저장돼야 한다."""
    res = client.post("/api/admin/residents", json={"name": "박복순"})
    assert res.status_code == 200
    (row,) = client.get("/api/admin/residents").json()
    assert row["phone"] == ""


def test_119_screen_reads_hyphenated_number(client):
    rid = client.post("/api/admin/residents", json={
        "name": "김순자", "room": "302호", "phone": "01012345678"}).json()["id"]
    cid = client.post("/api/admin/cameras", json={
        "device_key": "k1", "name": "방", "location": "세대 내부",
        "resident_id": rid}).json()["id"]

    info = client.get(f"/api/admin/cameras/{cid}/dispatch").json()
    assert info["phone"] == "010-1234-5678"


def test_seed_sample_already_matches_the_format():
    """시드 표본이 형식에서 어긋나면 화면 첫 인상부터 규칙이 깨져 보인다."""
    for _name, _age, _room, phone, _note in seed._RESIDENTS:
        assert cameras.normalize_phone(phone) == phone
