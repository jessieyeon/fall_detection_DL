"""영상 → 사람 체류 히트맵. YOLO는 지연 임포트하고 검출은 주입 가능하게 둔다.

frames_to_heatmap 은 순수(프레임 + detect 함수)라 YOLO 없이 테스트된다.
analyze_video 는 그 위의 얇은 래퍼로, 실제 YOLO11 트래킹을 붙인다.
"""

from webservice.consulting.heatmap import accumulate_heatmap


def frames_to_heatmap(frames, detect):
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


def _iter_frames(video_path):
    import cv2
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"영상을 열 수 없습니다: {video_path}")
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            yield frame
    finally:
        cap.release()


def _yolo_detector(model_name):
    from ultralytics import YOLO  # 지연 임포트 — 무거운 torch를 데모 밖에서 강제하지 않는다
    model = YOLO(model_name)

    def detect(frame):
        results = model.track(frame, persist=True, classes=[0],
                              conf=0.15, iou=0.45, verbose=False)
        boxes = []
        if results and results[0].boxes is not None:
            for b in results[0].boxes.xyxy.cpu().numpy():
                boxes.append(tuple(float(v) for v in b))
        return boxes

    return detect


def analyze_video(video_path, model_name="yolo11m.pt"):
    return frames_to_heatmap(_iter_frames(video_path), _yolo_detector(model_name))
