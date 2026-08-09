import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    dbfile = os.path.join(tmp_path, "t.db")
    monkeypatch.setattr("webservice.db.DB_PATH", dbfile)
    monkeypatch.setenv("DAON_DEMO_DEVICES", "")      # 시연용 가짜 기기는 끄고 본다
    from webservice import cameras, db, seed, app as app_module
    seed.seed_demo(dbfile)
    cameras.registry._seen.clear()
    c = TestClient(app_module.app)
    c.post("/api/auth/login",
           json={"email": seed.ADMIN_EMAIL, "password": seed.ADMIN_PW})
    return c


def test_requires_login(tmp_path, monkeypatch):
    dbfile = os.path.join(tmp_path, "t2.db")
    monkeypatch.setattr("webservice.db.DB_PATH", dbfile)
    from webservice import db, app as app_module
    db.init_db(dbfile)
    assert TestClient(app_module.app).get("/api/admin/cameras").status_code == 401


def test_meta_exposes_locations(client):
    from webservice import db
    assert client.get("/api/admin/meta").json()["locations"] == list(db.LOCATIONS)


# ── 입주민 ────────────────────────────────────────────────────────────

def test_resident_crud(client):
    before = len(client.get("/api/admin/residents").json())

    rid = client.post("/api/admin/residents",
                      json={"name": "최복순", "age": 79, "room": "208호"}).json()["id"]
    rows = client.get("/api/admin/residents").json()
    assert len(rows) == before + 1
    assert any(r["id"] == rid and r["age"] == 79 for r in rows)

    assert client.patch(f"/api/admin/residents/{rid}",
                        json={"room": "209호"}).status_code == 200
    moved = [r for r in client.get("/api/admin/residents").json() if r["id"] == rid][0]
    assert moved["room"] == "209호"

    assert client.delete(f"/api/admin/residents/{rid}").status_code == 200
    assert len(client.get("/api/admin/residents").json()) == before


def test_resident_name_required(client):
    r = client.post("/api/admin/residents", json={"name": "   "})
    assert r.status_code == 400 and "이름" in r.json()["detail"]


def test_resident_address_round_trip(client):
    """개별 주소가 저장·수정·조회 전 구간을 돈다."""
    rid = client.post("/api/admin/residents",
                      json={"name": "홍말녀", "address": "서울시 마포구 1"}).json()["id"]
    row = next(r for r in client.get("/api/admin/residents").json() if r["id"] == rid)
    assert row["address"] == "서울시 마포구 1"

    client.patch(f"/api/admin/residents/{rid}", json={"address": "서울시 마포구 2"})
    row = next(r for r in client.get("/api/admin/residents").json() if r["id"] == rid)
    assert row["address"] == "서울시 마포구 2"


def _link_first_camera(client):
    """시드 카메라(1층 라운지)를 시드 입주민(김순자)에 연결하고 둘을 돌려준다.

    시드는 최소 표본이라 연결된 카메라가 없다 — 연결이 필요한 테스트는
    여기서 직접 만든다.
    """
    cam = client.get("/api/admin/cameras").json()[0]
    resident = client.get("/api/admin/residents").json()[0]
    assert client.patch(f"/api/admin/cameras/{cam['id']}",
                        json={"resident_id": resident["id"]}).status_code == 200
    return cam, resident


def test_deleting_resident_keeps_camera(client):
    """입주민을 지워도 카메라는 남아야 한다 — 장비는 벽에 그대로 붙어 있다."""
    cam, resident = _link_first_camera(client)

    assert client.delete(f"/api/admin/residents/{resident['id']}").status_code == 200

    after = {c["id"]: c for c in client.get("/api/admin/cameras").json()}
    assert cam["id"] in after
    assert after[cam["id"]]["resident_id"] is None


# ── 카메라 ────────────────────────────────────────────────────────────

def test_camera_list_reports_offline_without_signal(client):
    assert all(c["online"] is False for c in client.get("/api/admin/cameras").json())


def test_scan_finds_only_unregistered_devices(client):
    from webservice import cameras
    cameras.registry.announce("daon-cam-lounge-1")        # 이미 등록된 기기
    cameras.registry.announce("daon-cam-new-1")      # 처음 보는 기기

    found = {d["device_key"] for d in client.get("/api/admin/cameras/scan").json()}
    assert found == {"daon-cam-new-1"}


def test_register_camera_from_scan(client):
    from webservice import cameras
    cameras.registry.announce("daon-cam-new-2")
    cid = client.post("/api/admin/cameras",
                      json={"device_key": "daon-cam-new-2", "name": "2층 복도",
                            "location": "복도"}).json()["id"]

    assert "daon-cam-new-2" not in {
        d["device_key"] for d in client.get("/api/admin/cameras/scan").json()}
    assert cid in {c["id"] for c in client.get("/api/admin/cameras").json()}


def test_register_rejects_unknown_location(client):
    r = client.post("/api/admin/cameras",
                    json={"device_key": "x-1", "name": "카메라", "location": "부엌"})
    assert r.status_code == 400 and "설치 공간" in r.json()["detail"]


def test_register_rejects_duplicate_device(client):
    r = client.post("/api/admin/cameras",
                    json={"device_key": "daon-cam-lounge-1", "name": "중복",
                          "location": "복도"})
    assert r.status_code == 400 and "이미 등록" in r.json()["detail"]


def test_camera_resident_can_be_cleared_and_set(client):
    cam, resident = _link_first_camera(client)
    original = resident["id"]

    client.patch(f"/api/admin/cameras/{cam['id']}", json={"clear_resident": True})
    now = {c["id"]: c for c in client.get("/api/admin/cameras").json()}
    assert now[cam["id"]]["resident_id"] is None

    client.patch(f"/api/admin/cameras/{cam['id']}", json={"resident_id": original})
    now = {c["id"]: c for c in client.get("/api/admin/cameras").json()}
    assert now[cam["id"]]["resident_id"] == original


# ── 119 신고 지원 ─────────────────────────────────────────────────────

def _set_facility(client):
    """시드는 시설 정보를 비워두므로, 신고 지원 테스트는 직접 채우고 시작한다."""
    client.patch("/api/admin/facility",
                 json={"facility_name": "다온실버타운", "address": "서울시 서대문구 1"})


def test_dispatch_with_linked_resident_names_the_person(client):
    _set_facility(client)
    cam, _ = _link_first_camera(client)

    info = client.get(f"/api/admin/cameras/{cam['id']}/dispatch").json()
    assert info["identified"] is True
    assert info["resident_name"] and info["room"]
    assert info["room"] in info["dispatch_address"]
    assert info["facility_name"] in info["dispatch_address"]


def test_dispatch_for_common_area_falls_back_to_facility(client):
    _set_facility(client)
    cam = client.get("/api/admin/cameras").json()[0]   # 시드 카메라는 연결이 없다

    info = client.get(f"/api/admin/cameras/{cam['id']}/dispatch").json()
    assert info["identified"] is False
    assert info["resident_name"] is None
    # 대상자는 몰라도 어디로 가야 하는지는 확정돼야 한다.
    assert info["facility_name"] in info["dispatch_address"]
    assert cam["location"] in info["dispatch_address"]


def test_resident_own_address_overrides_facility(client):
    """시설 밖에 사는 어르신은 개별 주소가 출동지다 — 시설 주소를 섞으면 안 된다."""
    _set_facility(client)
    rid = client.post("/api/admin/residents",
                      json={"name": "정순옥", "room": "201호",
                            "address": "경기도 고양시 9"}).json()["id"]
    cam = client.get("/api/admin/cameras").json()[0]
    client.patch(f"/api/admin/cameras/{cam['id']}", json={"resident_id": rid})

    addr = client.get(f"/api/admin/cameras/{cam['id']}/dispatch").json()["dispatch_address"]
    assert "경기도 고양시 9" in addr
    assert "다온실버타운" not in addr and "서대문구" not in addr


def test_dispatch_unknown_camera_404(client):
    assert client.get("/api/admin/cameras/9999/dispatch").status_code == 404


# ── 시설 정보 ─────────────────────────────────────────────────────────

def test_facility_update_changes_dispatch_address(client):
    _set_facility(client)
    client.patch("/api/admin/facility",
                 json={"facility_name": "새이름실버타운", "address": "부산시 어딘가"})
    cam = client.get("/api/admin/cameras").json()[0]
    info = client.get(f"/api/admin/cameras/{cam['id']}/dispatch").json()
    assert "새이름실버타운" in info["dispatch_address"]
    assert "부산시 어딘가" in info["dispatch_address"]
