"""업로드 영상 정규화 테스트.

핵심: OpenCV 가 읽을 수 있는 파일은 건드리지 않고, 못 읽는 파일만 변환하며,
변환도 불가능하면 사용자가 이해할 수 있는 메시지로 실패해야 한다.
"""

import os
import subprocess

import numpy as np
import pytest

from webservice.consulting import transcode


def _make_playable(path, frames=10, size=(64, 48)):
    """OpenCV 로 읽을 수 있는 mp4 를 만든다."""
    import cv2
    w, h = size
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 10, (w, h))
    if not writer.isOpened():
        pytest.skip("이 환경의 OpenCV 로 mp4 를 쓸 수 없습니다")
    for i in range(frames):
        frame = np.full((h, w, 3), i * 20 % 255, dtype=np.uint8)
        writer.write(frame)
    writer.release()
    return path


def test_opencv_can_read_detects_playable(tmp_path):
    path = _make_playable(os.path.join(tmp_path, "ok.mp4"))
    assert transcode.opencv_can_read(path) is True


def test_opencv_can_read_rejects_garbage(tmp_path):
    path = os.path.join(tmp_path, "bad.mov")
    with open(path, "wb") as f:
        f.write(b"not a video at all")
    assert transcode.opencv_can_read(path) is False


def test_readable_file_is_not_transcoded(tmp_path, monkeypatch):
    """이미 읽을 수 있는 파일을 재인코딩하면 시간 낭비이고 화질만 떨어진다."""
    path = _make_playable(os.path.join(tmp_path, "ok.mp4"))

    def boom(*a, **k):
        raise AssertionError("변환하면 안 되는 파일인데 변환을 시도했다")
    monkeypatch.setattr(transcode, "transcode", boom)

    out, converted = transcode.ensure_readable(path)
    assert out == path and converted is False


def test_unreadable_without_ffmpeg_raises_clear_error(tmp_path, monkeypatch):
    path = os.path.join(tmp_path, "hevc.mov")
    with open(path, "wb") as f:
        f.write(b"pretend this is HEVC")
    monkeypatch.setattr(transcode, "has_ffmpeg", lambda: False)

    with pytest.raises(transcode.TranscodeError) as exc:
        transcode.ensure_readable(path)
    assert "ffmpeg" in str(exc.value)


def test_transcode_missing_binary_raises_transcode_error(tmp_path, monkeypatch):
    monkeypatch.setattr(transcode, "ffmpeg_path", lambda: "definitely-not-a-binary")
    with pytest.raises(transcode.TranscodeError):
        transcode.transcode("in.mov", os.path.join(tmp_path, "out.mp4"))


def test_transcode_reports_ffmpeg_failure(tmp_path, monkeypatch):
    class Failed:
        returncode = 1
        stderr = b"Invalid data found when processing input"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Failed())

    with pytest.raises(transcode.TranscodeError) as exc:
        transcode.transcode("in.mov", os.path.join(tmp_path, "out.mp4"))
    assert "Invalid data" in str(exc.value)


def test_transcode_timeout_is_bounded(tmp_path, monkeypatch):
    def slow(*a, **k):
        raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=transcode.TIMEOUT_SEC)
    monkeypatch.setattr(subprocess, "run", slow)

    with pytest.raises(transcode.TranscodeError) as exc:
        transcode.transcode("in.mov", os.path.join(tmp_path, "out.mp4"))
    assert "초" in str(exc.value)


@pytest.mark.skipif(not transcode.has_ffmpeg(), reason="ffmpeg 가 없습니다")
def test_real_transcode_downscales_and_stays_readable(tmp_path):
    """ffmpeg 가 있는 환경에서 실제 변환이 동작하고 해상도가 줄어드는지."""
    import cv2
    src = _make_playable(os.path.join(tmp_path, "big.mp4"), size=(1920, 1080))
    dst = os.path.join(tmp_path, "small.mp4")
    transcode.transcode(src, dst, long_edge=320)

    assert transcode.opencv_can_read(dst)
    cap = cv2.VideoCapture(dst)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    assert max(w, h) <= 320
    assert w > h                     # 가로 영상의 비율이 유지됐다
