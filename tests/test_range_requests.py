"""정적 파일(특히 영상)의 HTTP Range 응답.

영상 재생바를 끌어도 안 움직이는데 새로고침하면 되기도 하던 증상의 원인이다.
starlette 0.37.2 의 FileResponse 는 Range 헤더를 무시하고 항상 200 + 전체를
돌려주는데, 브라우저는 206 을 못 받으면 아직 받지 않은 지점으로 건너뛸 수
없다. 파일이 이미 캐시에 다 들어와 있을 때만 탐색이 되니 '가끔 된다'로 보였다.
"""

import os

import pytest
from fastapi.testclient import TestClient

from webservice.app import _parse_range


# ── 범위 파싱 ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("header,size,expected", [
    ("bytes=0-99", 1000, (0, 99)),
    ("bytes=100-", 1000, (100, 999)),
    ("bytes=-200", 1000, (800, 999)),          # 끝에서부터
    ("bytes=0-99999", 1000, (0, 999)),         # 끝을 넘으면 파일 끝으로 자른다
    ("bytes=0-0", 1000, (0, 0)),
])
def test_parses_single_range(header, size, expected):
    assert _parse_range(header, size) == expected


@pytest.mark.parametrize("header", [
    None, "", "items=0-10",
    "bytes=0-99,200-299",     # 다중 구간은 다루지 않는다(브라우저가 안 쓴다)
    "bytes=abc-def",
    "bytes=500-100",          # 시작이 끝보다 뒤
    "bytes=2000-",            # 파일 밖
])
def test_unusable_ranges_fall_back_to_whole_file(header):
    assert _parse_range(header, 1000) is None


# ── 실제 응답 ─────────────────────────────────────────────────────────

BODY = bytes(range(256)) * 40          # 10240 바이트


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """dist 를 흉내 낸 임시 디렉터리로 SPA 라우트를 띄운다."""
    dist = tmp_path / "dist"
    (dist / "samples").mkdir(parents=True)
    (dist / "index.html").write_text("<html></html>")
    (dist / "samples" / "unit.mp4").write_bytes(BODY)

    # app 모듈은 임포트 시점에 _DIST 를 보고 라우트를 단다. 여기서는 이미 붙어
    # 있는 라우트가 다른 디렉터리를 보게만 하면 되므로 상수만 바꾼다.
    from webservice import app as app_module
    monkeypatch.setattr(app_module, "_DIST", str(dist))
    with TestClient(app_module.app) as c:
        yield c


def test_range_request_returns_206_slice(client):
    res = client.get("/samples/unit.mp4", headers={"Range": "bytes=100-199"})
    assert res.status_code == 206
    assert res.content == BODY[100:200]
    assert res.headers["content-range"] == f"bytes 100-199/{len(BODY)}"
    assert res.headers["content-length"] == "100"


def test_seek_to_middle_of_file(client):
    """재생바를 중간으로 끌었을 때 브라우저가 보내는 모양."""
    start = len(BODY) // 2
    res = client.get("/samples/unit.mp4", headers={"Range": f"bytes={start}-"})
    assert res.status_code == 206
    assert res.content == BODY[start:]


def test_plain_request_advertises_range_support(client):
    """Range 없이 받아도 Accept-Ranges 가 있어야 브라우저가 탐색을 시도한다."""
    res = client.get("/samples/unit.mp4")
    assert res.status_code == 200
    assert res.headers["accept-ranges"] == "bytes"
    assert res.content == BODY


def test_content_type_is_still_video(client):
    res = client.get("/samples/unit.mp4", headers={"Range": "bytes=0-9"})
    assert res.headers["content-type"].startswith("video/")


def test_head_request_still_reports_video(client):
    """컨설팅 화면이 샘플 존재 여부를 HEAD + content-type 으로 판단한다."""
    res = client.head("/samples/unit.mp4")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("video/")


def test_unknown_path_still_falls_back_to_index(client):
    res = client.get("/mypage")
    assert res.status_code == 200
    assert "<html>" in res.text


def test_range_cannot_escape_dist(client):
    res = client.get("/../../etc/passwd", headers={"Range": "bytes=0-10"})
    # 경로 탈출은 index.html 폴백으로 흡수된다(파일 내용이 새면 안 된다)
    assert b"root:" not in res.content


def test_zero_length_file_is_not_a_crash(client):
    """빈 파일에 범위를 요청해도 500 이 나면 안 된다.

    상태코드를 하나로 못 박지 않는 이유: 이 경우는 _parse_range 가 None 을
    돌려줘 FileResponse 로 넘기는데, 그 처리가 starlette 버전마다 다르다
    (0.37.2 는 200 + 빈 본문, 1.6 은 416). CI 는 버전을 고정하지 않아 배포용
    0.37.2 가 아닌 최신을 깔기 때문에 둘 다 지나갈 수 있어야 한다.
    빈 영상 파일은 배포가 깨진 경우라 어느 쪽 답이든 무방하다 — 여기서 지킬
    것은 '서버가 터지지 않는다' 하나다.
    """
    from webservice import app as app_module
    empty = os.path.join(app_module._DIST, "empty.mp4")
    open(empty, "wb").close()
    res = client.get("/empty.mp4", headers={"Range": "bytes=0-100"})
    assert res.status_code in (200, 206, 416)
    assert res.status_code < 500
