import os
import httpx
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    dbfile = os.path.join(tmp_path, "t.db")
    monkeypatch.setattr("webservice.db.DB_PATH", dbfile)
    from webservice import db, auth, app as app_module
    db.init_db(dbfile)
    conn = db.connect(dbfile)
    uid = auth.create_user(conn, "a@d.com", "pw", "admin", "관리자")
    conn.execute("UPDATE users SET address=?, facility_name=? WHERE id=?",
                 ("서울시 어딘가", "다온실버타운", uid))
    conn.commit()
    conn.close()
    c = TestClient(app_module.app)
    c.post("/api/auth/login", json={"email": "a@d.com", "password": "pw"})
    return c


def test_hospitals_uses_address(client, monkeypatch):
    monkeypatch.setenv("KAKAO_REST_KEY", "k")

    def handler(request):
        if "search/address.json" in str(request.url):
            return httpx.Response(200, json={"documents": [{"x": "127.1", "y": "37.5"}]})
        return httpx.Response(200, json={"documents": [
            {"place_name": "다온병원", "road_address_name": "도로명 1",
             "address_name": "", "phone": "", "distance": "100", "place_url": ""}]})

    monkeypatch.setattr("webservice.routes_home._client_factory",
                        lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    out = client.get("/api/home/hospitals").json()
    assert out[0]["name"] == "다온병원"


def test_hospitals_upstream_error_502(client, monkeypatch):
    monkeypatch.setenv("KAKAO_REST_KEY", "k")
    handler = lambda request: httpx.Response(401, json={"msg": "unauthorized"})
    monkeypatch.setattr("webservice.routes_home._client_factory",
                        lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    assert client.get("/api/home/hospitals").status_code == 502


def test_hospitals_requires_login(tmp_path, monkeypatch):
    dbfile = os.path.join(tmp_path, "t2.db")
    monkeypatch.setattr("webservice.db.DB_PATH", dbfile)
    from webservice import db, app as app_module
    db.init_db(dbfile)
    assert TestClient(app_module.app).get("/api/home/hospitals").status_code == 401
