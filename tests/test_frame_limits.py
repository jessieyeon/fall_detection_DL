"""분석 프레임 상한 테스트.

`DAON_ANALYZE_MAX_SECONDS` 는 온라인 전시의 부하 방어선 중 하나다. 관람객이
5분짜리 영상을 올려도 서버는 앞부분만 보고 끝내야 한다. 값만 있고 실제로
끊기는지 확인하는 테스트가 없으면, 샘플링 로직을 손볼 때 조용히 무력화된다.
"""

import os

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")


@pytest.fixture
def long_video(tmp_path):
    """30fps · 10초짜리 작은 영상."""
    path = os.path.join(tmp_path, "long.mp4")
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 30, (64, 64))
    if not writer.isOpened():
        pytest.skip("이 환경의 OpenCV 로는 mp4 를 쓸 수 없습니다")
    for i in range(300):
        writer.write(np.full((64, 64, 3), i % 255, dtype=np.uint8))
    writer.release()
    if not os.path.getsize(path):
        pytest.skip("영상 파일이 만들어지지 않았습니다")
    return path


def _count(path, **kw):
    from webservice.consulting.analyze import _iter_frames
    return sum(1 for _ in _iter_frames(path, **kw))


def test_long_video_is_truncated(long_video):
    """상한을 넘는 영상은 앞부분만 읽는다."""
    n = _count(long_video, target_fps=3, max_seconds=2)
    assert n <= 6, f"2초 상한인데 {n}프레임을 읽었다"


def test_short_video_is_not_truncated(long_video):
    """상한 안쪽 영상은 온전히 읽는다 — 상한이 정상 분석을 깎으면 안 된다."""
    full = _count(long_video, target_fps=3, max_seconds=0)     # 0 = 무제한
    within = _count(long_video, target_fps=3, max_seconds=60)
    assert within == full


def test_sampling_reduces_frame_count(long_video):
    """초당 3프레임 샘플링. 300프레임을 전부 디코딩하지 않는다."""
    assert _count(long_video, target_fps=3, max_seconds=0) < 60


def test_default_limit_is_configured():
    """기본 상한이 켜져 있어야 한다(0 이면 무제한이라 방어가 사라진다)."""
    from webservice.consulting import analyze
    assert analyze.MAX_SECONDS > 0
