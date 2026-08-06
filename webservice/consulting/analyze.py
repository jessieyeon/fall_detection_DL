"""영상 → 동선(통행량) 지도. YOLO는 지연 임포트하고 검출은 주입 가능하게 둔다.

`frames_to_passage` / `frames_to_heatmap` 은 순수(프레임 + detect 함수)라 YOLO 없이
테스트된다. `analyze_video` 는 그 위의 얇은 래퍼로, 실제 YOLO11 검출을 붙인다.

## 속도에 대해

원래 구현은 **모든 프레임**에 **yolo11m** 을 `model.track()` 으로 돌렸다. CPU에서
30초·30fps 영상이면 900회 추론이라 5~15분이 걸려 온라인 체험에 쓸 수 없었다.
네 가지를 바꿔 초 단위로 줄였다.

1. 프레임 샘플링(`TARGET_FPS`) — 동선 지도에 30fps는 불필요하다. 초당 3프레임이면
   사람이 방을 가로지르는 경로가 충분히 촘촘하게 찍힌다.
2. `yolo11m` → `yolo11n` — 가정 내 영상에 사람은 보통 한 명이고 크게 잡힌다.
   nano 로도 검출률이 떨어지지 않는다.
3. `imgsz=384` — 기본 640 대비 추론량이 줄어든다. 발끝 좌표를 몇 픽셀 단위로
   정확히 잡을 필요는 없다.
4. `track()` → `predict()` — 사람이 한 명이라 ID 추적이 필요 없다. 궤적은
   heatmap.extract_path 가 프레임 순서로 이어 붙인다.

전부 환경변수로 덮어쓸 수 있게 해뒀다(리허설 중 코드를 고치지 않기 위해).
"""

import os
import threading

from webservice.consulting.heatmap import (
    accumulate_heatmap,
    accumulate_passage_map,
    extract_path,
)

# 환경변수로 덮어쓸 수 있는 튜닝 값들
MODEL_NAME = os.environ.get("DAON_YOLO_MODEL", "yolo11n.pt")
TARGET_FPS = float(os.environ.get("DAON_ANALYZE_FPS", "3"))
IMGSZ = int(os.environ.get("DAON_YOLO_IMGSZ", "384"))
CONF = float(os.environ.get("DAON_YOLO_CONF", "0.15"))
MAX_SECONDS = float(os.environ.get("DAON_ANALYZE_MAX_SECONDS", "90"))


def frames_to_passage(frames, detect):
    """프레임 이터러블 + 검출 함수 → (통행량 지도, 첫 프레임, 동선 구간들)."""
    boxes_per_frame = []
    first = None
    height = width = None
    for frame in frames:
        if first is None:
            first = frame
            height, width = frame.shape[:2]
        boxes_per_frame.append(detect(frame))
    if first is None:
        raise ValueError("프레임이 없습니다")
    segments = extract_path(boxes_per_frame, height, width)
    return accumulate_passage_map(segments, height, width), first, segments


def frames_to_heatmap(frames, detect):
    """체류 히트맵(하위 호환). 동선 판정에는 frames_to_passage 를 쓴다."""
    boxes_per_frame = []
    first = None
    height = width = None
    for frame in frames:
        if first is None:
            first = frame
            height, width = frame.shape[:2]
        boxes_per_frame.append(detect(frame))
    if first is None:
        raise ValueError("프레임이 없습니다")
    return accumulate_heatmap(boxes_per_frame, height, width), first


def _iter_frames(video_path, target_fps=TARGET_FPS, max_seconds=MAX_SECONDS):
    """영상에서 초당 target_fps 장만 뽑아 순서대로 내보낸다.

    `cap.grab()` 은 디코드 없이 프레임을 건너뛰므로, 버릴 프레임에는
    `retrieve()` 를 부르지 않아 디코딩 비용까지 아낀다.
    """
    import cv2
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"영상을 열 수 없습니다: {video_path}")
    try:
        src_fps = cap.get(cv2.CAP_PROP_FPS)
        if not src_fps or src_fps <= 0 or src_fps != src_fps:   # 0 / NaN 방어
            src_fps = 30.0
        stride = max(1, int(round(src_fps / max(target_fps, 0.1))))
        limit = int(max_seconds * target_fps) if max_seconds > 0 else None

        idx = yielded = 0
        while True:
            ok = cap.grab()          # 디코드 없이 다음 프레임으로
            if not ok:
                break
            if idx % stride == 0:
                ok, frame = cap.retrieve()
                if not ok:
                    break
                yield frame
                yielded += 1
                if limit is not None and yielded >= limit:
                    break
            idx += 1
    finally:
        cap.release()


_MODEL_CACHE = {}
_MODEL_LOCK = threading.Lock()


def get_model(model_name=None):
    """가중치를 프로세스당 한 번만 읽고 재사용한다.

    예전에는 분석 요청마다 `YOLO(...)` 를 새로 만들었다. 가중치를 디스크에서
    다시 읽고 그래프를 다시 세우는 비용이 요청마다 붙어서, 짧은 영상에서는
    **추론보다 로딩이 더 오래 걸렸다**(24프레임 분석에 10초가 걸렸는데 그 중
    대부분이 로딩이었다). 캐시해두면 두 번째 요청부터 이 비용이 0이 된다.
    """
    name = model_name or MODEL_NAME
    with _MODEL_LOCK:
        if name not in _MODEL_CACHE:
            from ultralytics import YOLO  # 지연 임포트 — 무거운 torch를 데모 밖에서 강제하지 않는다
            _MODEL_CACHE[name] = YOLO(name)
        return _MODEL_CACHE[name]


def warmup(model_name=None):
    """모델을 미리 읽고 더미 추론을 한 번 돌려둔다.

    서버 기동 시 호출하면 첫 사용자가 로딩·최초 추론 지연을 떠안지 않는다.
    첫 추론은 지연 초기화(커널 컴파일, 메모리 할당) 때문에 이후보다 느리므로,
    가중치를 읽는 것만으로는 부족하고 한 번 돌려봐야 한다.
    """
    import numpy as np
    model = get_model(model_name)
    model.predict(np.zeros((IMGSZ, IMGSZ, 3), dtype=np.uint8),
                  imgsz=IMGSZ, verbose=False)
    return model


def _yolo_detector(model_name=None, imgsz=IMGSZ, conf=CONF):
    model = get_model(model_name)

    def detect(frame):
        # track() 이 아니라 predict(). 사람이 한 명이라 ID 추적이 불필요하고,
        # 트래커 상태 갱신 비용이 프레임마다 붙는다.
        results = model.predict(frame, classes=[0], conf=conf, iou=0.45,
                                imgsz=imgsz, verbose=False)
        boxes = []
        if results and results[0].boxes is not None:
            for b in results[0].boxes.xyxy.cpu().numpy():
                boxes.append(tuple(float(v) for v in b))
        return boxes

    return detect


def analyze_video(video_path, model_name=None):
    """영상 경로 → (통행량 지도, 첫 프레임, 동선 구간들)."""
    detect = _yolo_detector(model_name)
    return frames_to_passage(_iter_frames(video_path), detect)
