import os
import numpy as np
from webservice.consulting import heatmap


def test_empty_frames_zero_heatmap():
    hm = heatmap.accumulate_heatmap([], 40, 40)
    assert hm.shape == (40, 40) and hm.max() == 0.0


def test_box_region_is_hotter():
    # 좌상단에 박스가 있는 두 프레임 → 좌상단이 우하단보다 뜨겁다
    frames = [[(2, 2, 18, 18)], [(2, 2, 18, 18)]]
    hm = heatmap.accumulate_heatmap(frames, 40, 40, blur=5)
    assert hm[10, 10] > hm[35, 35]
    assert hm.dtype == np.float32


def test_render_writes_valid_image(tmp_path):
    import cv2
    hm = heatmap.accumulate_heatmap([[(2, 2, 18, 18)]], 40, 40, blur=5)
    out = os.path.join(tmp_path, "hm.png")
    heatmap.render_heatmap_png(hm, out)
    img = cv2.imread(out)
    assert img is not None and img.shape[:2] == (40, 40)


def test_hazard_boxes_marks_cell_red(tmp_path):
    import cv2
    frame = np.zeros((30, 30, 3), dtype=np.uint8)          # 검은 방
    findings = [{"cell": [0, 0], "level": "높음"}]           # 좌상단 셀이 위험
    out = os.path.join(tmp_path, "box.png")
    # 구역 박스는 기본으로 꺼져 있다(동선 전환 후 경로를 가려서). 명시적으로 켠다.
    heatmap.render_hazard_boxes(frame, findings, 3, 3, out, show_zone_box=True)
    img = cv2.imread(out)
    assert img is not None and img.shape == (30, 30, 3)
    # 좌상단(위험 셀)에는 빨강이 칠해지고, 우하단은 그대로 검정.
    # 셀 안쪽 픽셀을 찍는다 — 테두리 픽셀은 cv2 버전에 따라 굵기 오프셋이
    # 달라서 좌표가 한두 픽셀씩 어긋난다.
    b, g, r = img[5, 5]
    assert r > 50 and r > b and r > g        # 반투명(0.25) 빨강 채움
    assert img[27, 27].sum() < 30
