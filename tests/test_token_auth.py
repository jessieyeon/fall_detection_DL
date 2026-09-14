"""쿠키가 차단된 환경(전시 iframe + 인앱 브라우저)의 토큰 인증.

전시에서 실제로 난 사고를 고정한다: 로그인은 200 인데 Set-Cookie 가 저장되지
않아 이후 요청이 전부 401 이 됐다. 화면은 로그인된 것처럼 보이는데 아무것도
동작하지 않는 상태라 원인 파악이 오래 걸렸다.
"""

import os

import pytest
from fastapi.testclient import TestClient

from webservice import tokens


@pytest.fixture
def client(tmp_path, monkeypatch):
    dbfile = os.path.join(tmp_path, "t.db")
    monkeypatch.setattr("webservice.db.DB_PATH", dbfile)
    from webservice import db, auth, app as app_module
    db.init_db(dbfile)
    conn = db.connect(dbfile)
    auth.create_user(conn, "s@d.com", "pw", "admin", "김관리자")
    conn.commit(); conn.close()
    return TestClient(app_module.app)


def test_login_returns_token(client):
    r = client.post("/api/auth/login", json={"email": "s@d.com", "password": "pw"})
    assert r.status_code == 200
    assert r.json().get("token"), "로그인 응답에 토큰이 없으면 쿠키 차단 환경에서 인증 수단이 없다"


def test_token_works_without_cookie(client):
    token = client.post("/api/auth/login",
                        json={"email": "s@d.com", "password": "pw"}).json()["token"]
    client.cookies.clear()                       # 쿠키가 저장되지 않은 상황 재현
    assert client.get("/api/auth/me").status_code == 401
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == "s@d.com"


def test_upload_route_accepts_token(client):
    """전시에서 401 이 났던 바로 그 엔드포인트."""
    token = client.post("/api/auth/login",
                        json={"email": "s@d.com", "password": "pw"}).json()["token"]
    client.cookies.clear()
    r = client.post("/api/consulting/analyze",
                    files={"file": ("a.mp4", b"")},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code != 401, "토큰을 줬는데도 401 이면 폴백이 동작하지 않는 것"


def test_websocket_accepts_token_query(client):
    """WebSocket 은 커스텀 헤더를 못 붙여서 쿼리스트링으로 받아야 한다."""
    token = client.post("/api/auth/login",
                        json={"email": "s@d.com", "password": "pw"}).json()["token"]
    client.cookies.clear()
    with pytest.raises(Exception):               # 토큰 없으면 거부
        with client.websocket_connect("/ws/live"):
            pass
    with client.websocket_connect(f"/ws/live?token={token}"):
        pass                                      # 토큰이 있으면 붙는다


def test_forged_token_rejected(client):
    good = client.post("/api/auth/login",
                       json={"email": "s@d.com", "password": "pw"}).json()["token"]
    client.cookies.clear()
    bad = good[:-4] + "xxxx"
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {bad}"})
    assert r.status_code == 401


def test_malformed_header_is_rejected_not_crashed(client):
    for h in ("", "Bearer", "Basic abc", "Bearer  ", "Bearerxyz"):
        r = client.get("/api/auth/me", headers={"Authorization": h})
        assert r.status_code == 401, f"{h!r} 가 401 이 아니다"


def test_token_roundtrip_unit():
    u = {"id": 1, "email": "a@b.c", "role": "admin", "name": "홍길동", "facility_name": ""}
    assert tokens.read_token(tokens.make_token(u)) == u
    assert tokens.read_token("") is None
    assert tokens.read_token("not-a-token") is None
