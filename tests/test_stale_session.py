"""세션 쿠키에 남은 사용자가 DB 에 없을 때의 동작.

배포에서 실제로 났던 사고를 고정한다. 세션은 서명된 쿠키에만 있고 서버에
상태가 없어서, 컨테이너가 재시작돼 daon.db 가 새로 만들어져도 옛 쿠키는 그대로
유효했다. 그러면 '로그인은 되어 있는데' 그 id 가 users 에 없어서 쓰기가 전부

    sqlite3.IntegrityError: FOREIGN KEY constraint failed

로 죽었다 — 컨설팅 리포트 저장, 어르신 추가, 카메라 등록이 한꺼번에 실패한
원인이 이것이다. 읽기는 빈 목록을 돌려주므로 화면에서는 '저장만 안 되는'
것처럼 보였고, 그래서 원인을 찾기가 더 어려웠다.
"""

import pytest
from fastapi.testclient import TestClient

from webservice import auth, db, seed
from webservice.app import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    # 기동 시드가 표본 입주민·카메라까지 넣으면 '계정만 사라진 상태'를 만들기가
    # 번거로워진다. 계정은 이 픽스처가 직접 만든다.
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


def _wipe_users():
    """DB 는 살아 있는데 계정만 사라진 상태 — 재배포로 DB 가 갈린 상황.

    자식 행부터 지운다. users 를 먼저 지우면 그 DELETE 자체가 FK 로 막힌다.
    """
    conn = db.connect()
    try:
        conn.execute("DELETE FROM fall_events")
        conn.execute("DELETE FROM cameras")
        conn.execute("DELETE FROM residents")
        conn.execute("DELETE FROM reports")
        conn.execute("DELETE FROM users")
        conn.commit()
    finally:
        conn.close()


def test_resident_add_does_not_500_when_account_is_gone(client):
    _wipe_users()
    res = client.post("/api/admin/residents", json={"name": "김순자", "room": "302호"})
    # 예전에는 FOREIGN KEY 로 터져 500 + 'Internal Server Error' 였다.
    assert res.status_code == 401
    assert "다시 로그인" in res.json()["detail"]


def test_camera_register_does_not_500_when_account_is_gone(client):
    _wipe_users()
    res = client.post("/api/admin/cameras", json={
        "device_key": "daon-cam-lounge-2", "name": "라운지",
        "location": "공용 라운지"})
    assert res.status_code == 401


def test_analyze_rejected_before_running_when_account_is_gone(client):
    _wipe_users()
    res = client.post("/api/consulting/analyze",
                      files={"file": ("x.mp4", b"data", "video/mp4")},
                      data={"location": "세대 내부"})
    # 분석을 돌린 뒤 저장 단계에서 터지는 게 아니라, 시작 전에 막혀야 한다.
    assert res.status_code == 401


def test_session_recovers_when_account_is_recreated_with_new_id(client):
    """시드가 계정을 다시 만들면(=재배포) 세션이 새 id 를 따라가야 한다.

    이메일은 그대로이므로 관람객을 로그인 화면으로 돌려보낼 이유가 없다.
    """
    _wipe_users()
    conn = db.connect()
    try:
        # id 가 달라지도록 일부러 다른 번호로 넣는다
        conn.execute(
            "INSERT INTO users (id, email, pw_hash, role, name) VALUES (?,?,?,?,?)",
            (77, seed.ADMIN_EMAIL, auth.hash_password(seed.ADMIN_PW), "admin", "김관리자"))
        conn.commit()
    finally:
        conn.close()

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["id"] == 77

    res = client.post("/api/admin/residents", json={"name": "김순자", "room": "302호"})
    assert res.status_code == 200

    rows = client.get("/api/admin/residents").json()
    assert [r["name"] for r in rows] == ["김순자"]


def test_reads_also_reject_stale_session(client):
    _wipe_users()
    assert client.get("/api/admin/residents").status_code == 401
    # 세션이 비워졌으므로 두 번째 요청은 '로그인이 필요합니다' 쪽으로 떨어진다
    assert client.get("/api/admin/cameras").status_code == 401
