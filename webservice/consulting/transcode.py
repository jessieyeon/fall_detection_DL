"""업로드 영상 정규화 — OpenCV 가 읽을 수 있는 형식으로 맞춘다.

아이폰이 찍는 `.mov` 는 보통 HEVC(H.265)다. OpenCV 는 빌드에 포함된 FFmpeg
에 따라 HEVC 를 못 여는 경우가 많고, 그때 `VideoCapture.isOpened()` 가 False 를
돌려줄 뿐이라 "영상을 열 수 없습니다" 로 분석이 통째로 실패한다.

관람객이 폰으로 찍은 영상을 올리는 것이 체험의 핵심 동선이므로, 서버에서
한 번 H.264 로 변환하고 들어간다. OpenCV 가 이미 읽을 수 있는 파일은 변환하지
않는다(불필요한 재인코딩은 시간 낭비이고 화질도 떨어뜨린다).

동시에 해상도도 낮춘다. 1080p 원본을 그대로 디코딩할 이유가 없다 — YOLO 는
어차피 imgsz(기본 384)로 줄여서 추론하므로, 긴 변 720px 이면 충분하고 디코딩
비용만 줄어든다.
"""

import os
import shutil
import subprocess

# 긴 변 기준 최대 해상도. YOLO 입력(imgsz)보다 충분히 크면서 디코딩이 가벼운 값.
MAX_LONG_EDGE = int(os.environ.get("DAON_TRANSCODE_LONG_EDGE", "720"))
TIMEOUT_SEC = int(os.environ.get("DAON_TRANSCODE_TIMEOUT", "120"))


class TranscodeError(RuntimeError):
    """변환에 실패했고 원본도 읽을 수 없는 상태."""


def ffmpeg_path():
    return os.environ.get("DAON_FFMPEG", "ffmpeg")


def has_ffmpeg():
    return shutil.which(ffmpeg_path()) is not None


def opencv_can_read(path):
    """OpenCV 가 이 파일에서 실제로 프레임을 뽑을 수 있는지 확인한다.

    `isOpened()` 만으로는 부족하다. 컨테이너는 열리는데 코덱이 없어 첫
    `read()` 에서 실패하는 경우가 있다.
    """
    import cv2
    cap = cv2.VideoCapture(path)
    try:
        if not cap.isOpened():
            return False
        ok, frame = cap.read()
        return bool(ok) and frame is not None
    finally:
        cap.release()


def transcode(src, dst, long_edge=MAX_LONG_EDGE):
    """src → dst 로 H.264 재인코딩. 긴 변을 long_edge 로 축소한다."""
    # 긴 변만 제한하고 비율은 유지. -2 는 코덱이 요구하는 짝수 정렬을 맡긴다.
    scale = (f"scale='if(gt(iw,ih),min({long_edge},iw),-2)'"
             f":'if(gt(iw,ih),-2,min({long_edge},ih))'")
    cmd = [
        ffmpeg_path(), "-y", "-loglevel", "error",
        "-i", src,
        "-vf", scale,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
        "-pix_fmt", "yuv420p",     # 일부 플레이어/디코더 호환용
        "-an",                     # 오디오 불필요 — 분석은 영상만 본다
        dst,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=TIMEOUT_SEC)
    except FileNotFoundError:
        raise TranscodeError(
            "ffmpeg 를 찾을 수 없습니다. 서버에 ffmpeg 를 설치해야 "
            "아이폰(.mov/HEVC) 영상을 처리할 수 있습니다.")
    except subprocess.TimeoutExpired:
        raise TranscodeError(f"영상 변환이 {TIMEOUT_SEC}초를 넘겨 중단했습니다.")
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()[-500:]
        raise TranscodeError(f"영상 변환에 실패했습니다: {detail}")
    return dst


def ensure_readable(video_path, workdir=None):
    """분석 가능한 영상 경로를 돌려준다. 필요할 때만 변환한다.

    반환값은 (경로, 변환했는지 여부). 변환한 경우 호출자가 임시 파일을
    지울 책임을 진다.
    """
    if opencv_can_read(video_path):
        return video_path, False

    if not has_ffmpeg():
        raise TranscodeError(
            "이 영상 형식을 읽을 수 없습니다(아이폰 .mov 는 보통 HEVC 입니다). "
            "서버에 ffmpeg 가 설치되어 있지 않아 변환할 수도 없습니다.")

    base = workdir or os.path.dirname(video_path)
    stem = os.path.splitext(os.path.basename(video_path))[0]
    dst = os.path.join(base, f"{stem}__h264.mp4")
    transcode(video_path, dst)

    if not opencv_can_read(dst):
        raise TranscodeError("변환은 됐지만 결과 영상을 여전히 읽을 수 없습니다.")
    return dst, True
