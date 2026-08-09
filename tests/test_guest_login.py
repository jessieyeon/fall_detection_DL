"""'체험하기' 게스트 계정이 시드와 어긋나지 않는지.

관람객 동선의 첫 버튼이라 여기가 깨지면 체험 자체가 무산된다. 실제로
어르신·보호자 두 계정을 관리자 단일 계정으로 바꾸면서 프런트 상수만 남아
버튼이 통째로 죽은 적이 있어, 파일을 직접 읽어 대조한다.
"""

import os
import re

import pytest
from fastapi.testclient import TestClient

_LOGIN_TSX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "webservice", "frontend", "src", "pages", "Login.tsx")


def _guest_credentials():
    with open(_LOGIN_TSX, encoding="utf-8") as f:
        src = f.read()
    m = re.search(r'const GUEST = \{\s*email:\s*"([^"]+)",\s*password:\s*"([^"]+)"', src)
    assert m, "Login.tsx 에서 GUEST 상수를 찾지 못했습니다"
    return m.group(1), m.group(2)


def test_guest_matches_seed_account():
    from webservice import seed
    email, password = _guest_credentials()
    assert email == seed.ADMIN_EMAIL
    assert password == seed.ADMIN_PW


def test_guest_can_actually_log_in(tmp_path, monkeypatch):
    dbfile = os.path.join(tmp_path, "t.db")
    monkeypatch.setattr("webservice.db.DB_PATH", dbfile)
    from webservice import seed, app as app_module
    seed.seed_demo(dbfile)

    email, password = _guest_credentials()
    c = TestClient(app_module.app)
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, "체험하기 버튼이 쓰는 계정으로 로그인할 수 없습니다"
    # 로그인만 되고 아무것도 못 보면 체험이 안 된다 — 주요 화면 데이터까지 확인
    assert c.get("/api/admin/cameras").status_code == 200
    assert c.get("/api/admin/residents").status_code == 200
    assert c.get("/api/consulting/reports").status_code == 200
