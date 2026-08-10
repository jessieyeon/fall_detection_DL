"""어르신 상세 주소(동·호수).

카카오 우편번호 검색은 도로명까지만 준다. 나머지를 손으로 못 넣으면 119 에
읽어줄 주소가 건물 앞에서 끊긴다. address 에 이어 붙이지 않고 컬럼을 따로 둔
이유는 db.py 주석 참고 — 붙여 저장하면 수정 화면에서 되돌릴 수 없다.
"""

import pytest
from fastapi.testclient import TestClient

from webservice import auth, cameras, db, seed
from webservice.app import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    # 시드 표본(김순자)이 들어오면 목록 단언이 지저분해진다. 계정만 직접 만들고
    # 입주민은 각 테스트가 넣는 것만 있게 한다.
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


def test_detail_survives_create_and_read(client):
    client.post("/api/admin/residents", json={
        "name": "김순자", "room": "302호",
        "address": "서울 강남구 테헤란로 1", "address_detail": "101동 1203호"})
    (row,) = client.get("/api/admin/residents").json()
    assert row["address"] == "서울 강남구 테헤란로 1"
    assert row["address_detail"] == "101동 1203호"


def test_detail_can_be_edited_without_losing_the_searched_part(client):
    rid = client.post("/api/admin/residents", json={
        "name": "김순자", "address": "서울 강남구 테헤란로 1",
        "address_detail": "101동 1203호"}).json()["id"]
    client.patch(f"/api/admin/residents/{rid}", json={"address_detail": "102동 501호"})
    (row,) = client.get("/api/admin/residents").json()
    assert row["address"] == "서울 강남구 테헤란로 1"    # 검색 결과는 그대로
    assert row["address_detail"] == "102동 501호"


def test_detail_defaults_to_empty_for_old_rows(client):
    client.post("/api/admin/residents", json={"name": "박복순"})
    (row,) = client.get("/api/admin/residents").json()
    assert row["address_detail"] == ""


def test_119_address_includes_detail(client):
    rid = client.post("/api/admin/residents", json={
        "name": "김순자", "room": "302호",
        "address": "서울 강남구 테헤란로 1", "address_detail": "101동 1203호"}).json()["id"]
    cid = client.post("/api/admin/cameras", json={
        "device_key": "k1", "name": "방", "location": "세대 내부",
        "resident_id": rid}).json()["id"]

    info = client.get(f"/api/admin/cameras/{cid}/dispatch").json()
    assert info["dispatch_address"] == "서울 강남구 테헤란로 1 101동 1203호"


def test_119_falls_back_to_room_when_no_detail(client):
    """상세 주소 이전에 저장된 어르신도 예전처럼 호실이 붙어야 한다."""
    rid = client.post("/api/admin/residents", json={
        "name": "김순자", "room": "302호",
        "address": "서울 강남구 테헤란로 1"}).json()["id"]
    cid = client.post("/api/admin/cameras", json={
        "device_key": "k2", "name": "방", "location": "세대 내부",
        "resident_id": rid}).json()["id"]

    info = client.get(f"/api/admin/cameras/{cid}/dispatch").json()
    assert info["dispatch_address"] == "서울 강남구 테헤란로 1 302호"


def test_migration_adds_column_to_existing_db(tmp_path, monkeypatch):
    """상세 주소 컬럼이 없던 시절의 DB 도 그대로 열려야 한다."""
    path = str(tmp_path / "old.db")
    monkeypatch.setattr(db, "DB_PATH", path)
    conn = db.connect()
    conn.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT,
                            pw_hash TEXT, role TEXT, name TEXT,
                            facility_name TEXT DEFAULT '', address TEXT DEFAULT '');
        CREATE TABLE residents (id INTEGER PRIMARY KEY AUTOINCREMENT,
                                admin_id INTEGER NOT NULL REFERENCES users(id),
                                name TEXT NOT NULL, age INTEGER,
                                room TEXT DEFAULT '', phone TEXT DEFAULT '',
                                note TEXT DEFAULT '');
    """)
    conn.execute("INSERT INTO users (email, pw_hash, role, name) VALUES ('a','b','admin','c')")
    conn.execute("INSERT INTO residents (admin_id, name) VALUES (1, '김순자')")
    conn.commit()
    conn.close()

    db.init_db()                       # 마이그레이션

    conn = db.connect()
    try:
        assert cameras.list_residents(conn, 1) == [
            {"id": 1, "name": "김순자", "age": None, "room": "", "phone": "",
             "note": "", "address": "", "address_detail": ""}]
    finally:
        conn.close()


def test_whitespace_only_detail_is_stored_empty(client):
    client.post("/api/admin/residents", json={
        "name": "김순자", "address": "서울 강남구 테헤란로 1",
        "address_detail": "   "})
    (row,) = client.get("/api/admin/residents").json()
    assert row["address_detail"] == ""
