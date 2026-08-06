"""iframe 임베드 설정 테스트.

온라인 전시 사이트가 이 앱을 iframe 으로 띄운다. 여기가 틀리면 URL 을 직접
열었을 때는 멀쩡한데 iframe 안에서만 화면이 비거나 로그인이 풀린다 —
제출 직전에 발견하기 가장 나쁜 종류의 버그라 테스트로 고정한다.
"""

import importlib
import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_module(monkeypatch, tmp_path):
    monkeypatch.setenv("DAON_SKIP_WARMUP", "1")
    monkeypatch.setattr("webservice.db.DB_PATH", os.path.join(tmp_path, "t.db"))
    from webservice import app as app_module
    return importlib.reload(app_module)


def test_csp_allows_framing(app_module):
    r = TestClient(app_module.app).get("/api/health")
    assert "frame-ancestors *" in r.headers["content-security-policy"]


def test_no_x_frame_options(app_module):
    """X-Frame-Options 는 값이 있으면 무조건 막는다(ALLOW-FROM 은 폐기됨)."""
    r = TestClient(app_module.app).get("/api/health")
    assert "x-frame-options" not in {k.lower() for k in r.headers}


def test_frame_ancestors_can_be_restricted(monkeypatch, tmp_path):
    monkeypatch.setenv("DAON_SKIP_WARMUP", "1")
    monkeypatch.setenv("DAON_FRAME_ANCESTORS", "https://exhibition.example.com")
    monkeypatch.setattr("webservice.db.DB_PATH", os.path.join(tmp_path, "t.db"))
    from webservice import app as app_module
    mod = importlib.reload(app_module)

    r = TestClient(mod.app).get("/api/health")
    assert r.headers["content-security-policy"] == \
        "frame-ancestors https://exhibition.example.com"


def test_embed_mode_uses_samesite_none(monkeypatch, tmp_path):
    """iframe 안에서 세션 쿠키가 살아남으려면 SameSite=None; Secure 여야 한다."""
    monkeypatch.setenv("DAON_SKIP_WARMUP", "1")
    monkeypatch.setenv("DAON_EMBED", "1")
    monkeypatch.setattr("webservice.db.DB_PATH", os.path.join(tmp_path, "t.db"))
    from webservice import app as app_module
    mod = importlib.reload(app_module)
    assert mod._EMBED is True

    from starlette.middleware.sessions import SessionMiddleware
    session_mw = [m for m in mod.app.user_middleware
                  if m.cls is SessionMiddleware]
    assert session_mw, "SessionMiddleware 가 등록되어 있지 않다"
    kwargs = session_mw[0].kwargs
    assert kwargs["same_site"] == "none"
    assert kwargs["https_only"] is True


def test_local_mode_keeps_lax(app_module):
    """로컬 개발은 HTTP 라 Secure 쿠키를 못 쓴다 — 기본은 lax 여야 한다."""
    assert app_module._EMBED is False
    from starlette.middleware.sessions import SessionMiddleware
    mw = [m for m in app_module.app.user_middleware
          if m.cls is SessionMiddleware][0]
    assert mw.kwargs["same_site"] == "lax"
    assert mw.kwargs["https_only"] is False
