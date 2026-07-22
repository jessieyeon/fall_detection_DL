"""바닥 타일 격자의 호모그래피 캘리브레이션.

calibrate.py 가 저장한 calibration.json 을 읽어 픽셀 좌표와 격자 셀 사이를
변환한다. main.py 에서 그대로 옮겨온 코드이며, camera_yaw_deg 만 새로 읽는다.
"""

import json
import os

import cv2
import numpy as np

CALIBRATION_FILE = "calibration.json"


def load_tile_grid(path=CALIBRATION_FILE):
    """캘리브레이션을 읽어 격자 정보를 반환한다. 파일이 없으면 None."""
    if not os.path.isfile(path):
        print(f"경고: {path} 가 없습니다 - calibrate.py 를 먼저 실행하세요. "
              "격자 오버레이 없이 진행합니다.")
        return None

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    src = np.array(data["floor_corners_px"], dtype=np.float32)
    dst = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float32)
    homography = cv2.getPerspectiveTransform(src, dst)

    return {
        "rows": data["rows"],
        "cols": data["cols"],
        # 카메라 광축과 타일 격자 축의 각도 차이. 정면이면 0.
        "camera_yaw_deg": float(data.get("camera_yaw_deg", 0.0)),
        "homography": homography,
        "inverse_homography": np.linalg.inv(homography),
    }


def pixel_to_tile(foot_xy, tile_grid):
    """발 위치 픽셀 좌표를 (row, col, tile_index) 로 변환한다."""
    px = np.array([[foot_xy]], dtype=np.float32)
    u, v = cv2.perspectiveTransform(px, tile_grid["homography"])[0][0]
    u = min(max(u, 0.0), 0.999)
    v = min(max(v, 0.0), 0.999)
    col = int(u * tile_grid["cols"])
    row = int(v * tile_grid["rows"])
    return row, col, row * tile_grid["cols"] + col


def draw_tile_grid(frame, tile_grid, active_tiles=None):
    """프레임 위에 격자를 그리고 active_tiles 를 붉게 강조한다."""
    rows, cols = tile_grid["rows"], tile_grid["cols"]
    inv_h = tile_grid["inverse_homography"]

    def floor_to_px(u, v):
        pt = cv2.perspectiveTransform(np.array([[[u, v]]], dtype=np.float32), inv_h)[0][0]
        return int(pt[0]), int(pt[1])

    if active_tiles:
        overlay = frame.copy()
        for tile_index in active_tiles:
            row, col = divmod(tile_index, cols)
            corners = np.array([
                floor_to_px(col / cols, row / rows),
                floor_to_px((col + 1) / cols, row / rows),
                floor_to_px((col + 1) / cols, (row + 1) / rows),
                floor_to_px(col / cols, (row + 1) / rows),
            ], dtype=np.int32).reshape(-1, 1, 2)
            cv2.fillPoly(overlay, [corners], (0, 0, 255))
        cv2.addWeighted(overlay, 0.35, frame, 0.65, 0, dst=frame)

    for r in range(rows + 1):
        v = r / rows
        cv2.line(frame, floor_to_px(0, v), floor_to_px(1, v), (255, 200, 0), 1)
    for c in range(cols + 1):
        u = c / cols
        cv2.line(frame, floor_to_px(u, 0), floor_to_px(u, 1), (255, 200, 0), 1)
