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


def render_hazard_boxes(frame, findings, rows, cols, out_path):
    """캡처된 방 프레임 위에 위험 구역(격자 셀)을 반투명 빨간 박스 + 굵은 테두리로 표시.

    JET 그라디언트보다 '어느 방 구역이 위험한지'가 명확하다. findings 의 cell=[r,c] 를
    rows×cols 격자 셀로 환산해 그린다. 색은 위험 등급에 따른다(BGR).
    """
    img = frame.copy()
    h, w = img.shape[:2]
    ch, cw = h // rows, w // cols
    seen = set()
    for f in findings:
        cell = tuple(f["cell"])
        if cell in seen:
            continue
        seen.add(cell)
        r, c = cell
        x1, y1 = int(c * cw), int(r * ch)
        x2, y2 = int(x1 + cw), int(y1 + ch)
        col = (0, 0, 255) if f["level"] == "높음" else \
              (0, 140, 255) if f["level"] == "보통" else (170, 170, 170)
        overlay = img.copy()
        cv2.rectangle(overlay, (x1, y1), (x2, y2), col, -1)
        cv2.addWeighted(overlay, 0.25, img, 0.75, 0, dst=img)  # 반투명 채움
        cv2.rectangle(img, (x1, y1), (x2, y2), col, 4)          # 굵은 테두리
    cv2.imwrite(out_path, img)
