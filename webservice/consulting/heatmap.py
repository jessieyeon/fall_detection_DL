"""사람 바운딩박스 누적 히트맵. 순수 함수 — YOLO/torch 의존 없음.

친구 노트북(YOLO11 트래킹 → 박스 누적 히트맵) 기술을 이식한 것이며,
검출(박스 산출)은 이 모듈 밖(analyze.py)에서 이뤄진다.
"""

import cv2
import numpy as np


def accumulate_heatmap(boxes_per_frame, height, width, blur=51):
    heatmap = np.zeros((height, width), dtype=np.float32)
    # 커널은 홀수여야 한다
    k = blur if blur % 2 == 1 else blur + 1
    for boxes in boxes_per_frame:
        for (x1, y1, x2, y2) in boxes:
            mask = np.zeros((height, width), dtype=np.float32)
            cv2.rectangle(mask, (int(x1), int(y1)), (int(x2), int(y2)), 1.0, -1)
            mask = cv2.GaussianBlur(mask, (k, k), 0)
            heatmap += mask
    return heatmap


def render_heatmap_png(heatmap, out_path, background=None):
    norm = cv2.normalize(heatmap, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    color = cv2.applyColorMap(norm, cv2.COLORMAP_JET)
    if background is not None:
        color = cv2.addWeighted(background, 0.5, color, 0.5, 0)
    cv2.imwrite(out_path, color)
