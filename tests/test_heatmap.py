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
