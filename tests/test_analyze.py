import numpy as np
from webservice.consulting import analyze


def test_frames_to_heatmap_uses_injected_detector():
    # 합성 프레임 3장, 가짜 detect는 좌상단 박스만 반환
    frames = [np.zeros((40, 40, 3), dtype=np.uint8) for _ in range(3)]

    def fake_detect(frame):
        return [(2, 2, 18, 18)]

    hm, first = analyze.frames_to_heatmap(frames, fake_detect)
    assert hm.shape == (40, 40)
    # 좌상단 사분면이 우하단보다 뜨겁다 (큰 블러에도 견고하도록 사분면 합으로 비교)
    assert hm[:20, :20].sum() > hm[20:, 20:].sum()
    assert first.shape == (40, 40, 3)


def test_frames_to_heatmap_no_detections_is_cold():
    frames = [np.zeros((20, 20, 3), dtype=np.uint8)]
    hm, _ = analyze.frames_to_heatmap(frames, lambda f: [])
    assert hm.max() == 0.0


def test_analyze_video_is_importable_without_ultralytics():
    # 함수 존재만 확인 — 호출하면 지연 임포트가 ultralytics를 요구한다
    assert callable(analyze.analyze_video)
