"""세션 시크릿 방어 테스트.

`DAON_SECRET` 은 세션 쿠키 서명 키다. 저장소에 적힌 기본값 그대로 배포되면
누구나 다른 사람의 로그인 쿠키를 위조할 수 있다. 배포 직전 체크리스트의
"DAON_SECRET 이 실제 값인지" 항목을 사람 눈이 아니라 기동 조건으로 고정한다.

로컬 개발은 그대로 편해야 하므로, 배포 신호(DAON_EMBED=1)일 때만 막는다.
"""

import importlib
import os

import pytest


def _reload(monkeypatch, tmp_path, **env):
    monkeypatch.setenv("DAON_SKIP_WARMUP", "1")
    monkeypatch.delenv("DAON_SECRET", raising=False)
    monkeypatch.delenv("DAON_EMBED", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr("webservice.db.DB_PATH", os.path.join(tmp_path, "t.db"))
    from webservice import app as app_module
    return importlib.reload(app_module)


def test_deploy_with_default_secret_refuses_to_start(monkeypatch, tmp_path):
    """배포 모드 + 기본 시크릿이면 서버가 뜨면 안 된다."""
    with pytest.raises(RuntimeError, match="DAON_SECRET"):
        _reload(monkeypatch, tmp_path, DAON_EMBED="1")


def test_deploy_with_empty_secret_also_refuses(monkeypatch, tmp_path):
    """빈 문자열은 '설정했다'가 아니다 — 환경변수를 넣다 만 흔한 실수."""
    with pytest.raises(RuntimeError, match="DAON_SECRET"):
        _reload(monkeypatch, tmp_path, DAON_EMBED="1", DAON_SECRET="")


def test_deploy_with_real_secret_starts(monkeypatch, tmp_path):
    mod = _reload(monkeypatch, tmp_path,
                  DAON_EMBED="1", DAON_SECRET="a-real-random-value")
    assert mod._SECRET == "a-real-random-value"


def test_local_dev_still_works_without_secret(monkeypatch, tmp_path):
    """로컬은 시크릿 없이도 떠야 한다 — 개발을 막는 방어는 우회당한다."""
    mod = _reload(monkeypatch, tmp_path)
    assert mod._SECRET == mod.DEFAULT_SECRET


def test_error_message_says_how_to_fix_it(monkeypatch, tmp_path):
    """새벽 배포 중에 읽을 문장이다. 원인만이 아니라 해법이 들어 있어야 한다."""
    with pytest.raises(RuntimeError) as exc:
        _reload(monkeypatch, tmp_path, DAON_EMBED="1")
    assert "token_urlsafe" in str(exc.value)


@pytest.fixture(autouse=True)
def _restore(tmp_path, monkeypatch):
    """다른 테스트가 쓰는 app 모듈을 기본 상태로 되돌린다."""
    yield
    monkeypatch.delenv("DAON_SECRET", raising=False)
    monkeypatch.delenv("DAON_EMBED", raising=False)
    monkeypatch.setattr("webservice.db.DB_PATH", os.path.join(tmp_path, "t.db"))
    from webservice import app as app_module
    importlib.reload(app_module)
