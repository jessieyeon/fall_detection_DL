"""빌드된 SPA 정적 파일 서빙 규약.

프런트는 샘플 영상이 실제로 있는지 HEAD 로 먼저 확인한다. GET 만 열려 있으면
405 가 돌아와 파일이 멀쩡한데도 카드가 '영상을 준비 중입니다'로 죽는다.
시연 직전에야 발견되기 쉬운 종류의 사고라 회귀 테스트로 못 박아 둔다.
"""

import os

import pytest
from fastapi.testclient import TestClient

from webservice import app as app_module

_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "webservice", "frontend", "dist")

pytestmark = pytest.mark.skipif(
    not os.path.isdir(_DIST), reason="프런트를 아직 빌드하지 않음 (npm run build)")


@pytest.fixture
def client():
    return TestClient(app_module.app)


def _existing_sample():
    d = os.path.join(_DIST, "samples")
    if not os.path.isdir(d):
        return None
    for name in sorted(os.listdir(d)):
        if name.endswith(".mp4"):
            return f"/samples/{name}"
    return None


def test_head_on_static_file_is_allowed(client):
    """HEAD 로 존재 확인이 되어야 한다 — 405 면 프런트가 '준비 중'으로 오판한다."""
    path = _existing_sample()
    if path is None:
        pytest.skip("dist/samples 에 mp4 가 없음")

    r = client.head(path)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("video")


def test_head_on_spa_route_returns_html(client):
    """클라이언트 라우트는 여전히 index.html — HEAD 도 마찬가지."""
    r = client.head("/mypage")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")


def test_head_on_api_path_is_not_swallowed_by_spa(client):
    """/api/* 는 SPA 가 가로채지 않는다."""
    assert client.head("/api/definitely-not-a-route").status_code == 404
