"""동선(passage) 분석 테스트.

핵심 검증: 같은 자리에 오래 서 있는 영상과 그 자리를 여러 번 지나가는 영상을
구분하는가. 이게 '체류'와 '동선'의 차이이고, 컨설팅 기준의 근거다.
"""

import numpy as np
import pytest

from webservice.consulting import analyze, heatmap, rules

H = W = 300


def _box_at(x, y, w=30, h=60):
    """발끝이 (x, y)에 오는 바운딩박스."""
    return (x - w / 2, y - h, x + w / 2, y)


def _standing_frames(n=120, x=60, y=60):
    """제자리에 서 있음 — 검출 지터로 ±2px 흔들린다."""
    rng = np.random.default_rng(0)
    return [[_box_at(x + rng.integers(-2, 3), y + rng.integers(-2, 3))]
            for _ in range(n)]


def _walking_frames(passes=3, n_per_pass=40, y=240):
    """좌↔우를 passes 번 왕복하며 지나감."""
    frames = []
    for p in range(passes):
        xs = np.linspace(20, W - 20, n_per_pass)
        if p % 2:
            xs = xs[::-1]
        frames.extend([[_box_at(float(x), y)] for x in xs])
    return frames


# --------------------------------------------------------------------------
# 궤적 추출
# --------------------------------------------------------------------------

def test_foot_point_is_bottom_center():
    assert heatmap.foot_point((10, 20, 30, 80)) == (20.0, 80.0)


def test_foot_points_picks_largest_box():
    frames = [[(0, 0, 10, 10), (100, 100, 200, 260)]]
    pts = heatmap.foot_points(frames)
    assert pts == [(150.0, 260.0)]


def test_missing_detection_splits_segments():
    pts = [(1, 1), (2, 2), None, (9, 9), (10, 10)]
    segs = heatmap.split_segments(pts)
    assert len(segs) == 2 and segs[0] == [(1, 1), (2, 2)]


def test_short_gap_is_bridged_by_interpolation():
    """한두 프레임 놓친 것만으로 경로가 끊기면 안 된다.

    검출기는 가려짐·모션블러로 프레임을 종종 놓친다. 그때마다 구간을 자르면
    한 번의 이동이 여러 조각이 되고, 조각마다 첫 점만 남아 동선이 실제보다
    성기게 잡힌다.
    """
    pts = [(0, 0), (10, 0), None, (30, 0)]
    segs = heatmap.split_segments(pts, max_gap=3)
    assert len(segs) == 1
    assert (20.0, 0.0) in segs[0]        # 공백이 직선 보간으로 메워졌다


def test_long_gap_still_splits():
    """프레임 밖으로 나갔다 들어온 경우까지 이으면 없던 경로가 생긴다."""
    pts = [(0, 0), (10, 0)] + [None] * 8 + [(900, 500)]
    segs = heatmap.split_segments(pts, max_gap=3)
    assert len(segs) == 2


def test_gap_bridging_reduces_fragmentation():
    """실제 상황 재현: 검출이 드문드문 실패해도 하나의 동선으로 남아야 한다."""
    xs = np.linspace(20, W - 20, 60)
    frames = []
    for i, x in enumerate(xs):
        frames.append([] if i % 7 == 3 else [_box_at(float(x), 240)])

    bridged = heatmap.extract_path(frames, H, W, max_gap=3)
    fragmented = heatmap.extract_path(frames, H, W, max_gap=0)
    assert len(bridged) < len(fragmented)
    assert sum(len(s) for s in bridged) > sum(len(s) for s in fragmented)


def test_standing_still_collapses_to_few_points():
    """제자리 120프레임이 한 점 수준으로 접혀야 한다."""
    segs = heatmap.extract_path(_standing_frames(), H, W)
    total = sum(len(s) for s in segs)
    assert total <= 3, f"제자리인데 {total}개 점이 남았다"


def test_walking_keeps_many_points():
    segs = heatmap.extract_path(_walking_frames(), H, W)
    total = sum(len(s) for s in segs)
    assert total > 20, f"걸었는데 {total}개 점밖에 안 남았다"


# --------------------------------------------------------------------------
# 통행량 지도 — 체류 대비 동선의 핵심 차이
# --------------------------------------------------------------------------

# 두 구역은 넓이가 달라(100×100 vs 100×300) 합계로 비교하면 넓은 쪽이 유리하다.
# 넓이에 영향받지 않는 최대값으로 비교한다.

def test_passage_map_favours_walking_over_standing():
    """오래 선 자리보다 자주 지난 경로가 더 뜨거워야 한다.

    체류 히트맵이었다면 정반대 결과가 나온다(아래 대조 테스트 참고).
    """
    frames = _standing_frames(n=200) + _walking_frames(passes=3)
    segs = heatmap.extract_path(frames, H, W)
    pmap = heatmap.accumulate_passage_map(segs, H, W)

    standing_zone = pmap[0:100, 0:100].max()     # 200프레임 서 있던 좌상단
    walking_zone = pmap[200:300, :].max()        # 3회 왕복한 하단 통로
    assert walking_zone > standing_zone * 2


def test_dwell_heatmap_shows_the_opposite():
    """대조군: 기존 체류 히트맵은 서 있던 자리를 더 뜨겁게 본다.

    같은 입력에 두 지도가 정반대 결론을 내는 것이 이번 변경의 핵심이다.
    """
    frames = _standing_frames(n=200) + _walking_frames(passes=3)
    hm = heatmap.accumulate_heatmap(frames, H, W)
    assert hm[0:100, 0:100].max() > hm[200:300, :].max()


def test_passage_value_tracks_number_of_passes():
    """통과 횟수가 늘면 값도 그만큼 커져야 한다(대략 비례).

    '자주 지나다니는 동선'을 재겠다고 했으므로, 값이 실제 통과 횟수를
    반영하지 않으면 컨설팅 근거가 성립하지 않는다.
    """
    peaks = []
    for n in (1, 2, 4):
        segs = heatmap.extract_path(_walking_frames(passes=n), H, W)
        peaks.append(float(heatmap.accumulate_passage_map(segs, H, W).max()))

    assert peaks[0] < peaks[1] < peaks[2]
    # 4회는 1회의 3~5배 (완전 선형은 아니지만 배율이 유지돼야 한다)
    assert 3.0 <= peaks[2] / peaks[0] <= 5.0


def test_overlapping_points_actually_accumulate():
    """같은 지점을 여러 번 찍으면 값이 쌓여야 한다.

    회귀 방지: cv2.circle 로 원을 그리면 값이 덮어써져서, 같은 자리를 몇 번
    지나든 결과가 똑같아진다.
    """
    once = heatmap.accumulate_passage_map([[(150.0, 150.0)]], H, W)
    thrice = heatmap.accumulate_passage_map(
        [[(150.0, 150.0)], [(150.0, 150.0)], [(150.0, 150.0)]], H, W)
    assert thrice.max() > once.max() * 2.5


def test_dwell_boxes_accumulate_too():
    """회귀 방지: 체류 지도도 겹치는 박스가 쌓여야 한다."""
    one = heatmap.accumulate_heatmap([[(50, 50, 100, 100)]], H, W, blur=5)
    three = heatmap.accumulate_heatmap(
        [[(50, 50, 100, 100)]] * 3, H, W, blur=5)
    assert three.max() > one.max() * 2.5


def test_empty_segments_give_cold_map():
    pmap = heatmap.accumulate_passage_map([], H, W)
    assert pmap.shape == (H, W) and pmap.max() == 0.0
    assert pmap.dtype == np.float32


# --------------------------------------------------------------------------
# analyze 계층
# --------------------------------------------------------------------------

def test_frames_to_passage_returns_map_first_and_segments():
    frames = [np.zeros((H, W, 3), dtype=np.uint8) for _ in range(60)]
    xs = np.linspace(20, W - 20, 60)
    boxes = [[_box_at(float(x), 240)] for x in xs]
    it = iter(boxes)

    pmap, first, segments = analyze.frames_to_passage(frames, lambda f: next(it))
    assert pmap.shape == (H, W)
    assert first.shape == (H, W, 3)
    assert segments and sum(len(s) for s in segments) > 5


def test_frames_to_passage_rejects_empty():
    with pytest.raises(ValueError):
        analyze.frames_to_passage([], lambda f: [])


def test_analyze_video_importable_without_ultralytics():
    assert callable(analyze.analyze_video)


# --------------------------------------------------------------------------
# 규칙 문구
# --------------------------------------------------------------------------

def test_report_language_is_about_movement_not_dwelling():
    segs = heatmap.extract_path(_walking_frames(passes=3), H, W)
    pmap = heatmap.accumulate_passage_map(segs, H, W)
    report = rules.analyze_report(pmap)

    text = report["summary"] + " ".join(f["recommendation"] for f in report["findings"])
    assert "머무" not in text and "체류" not in text
    assert "지나" in text or "통행" in text or "동선" in text


def test_top_finding_is_the_walked_row():
    """하단을 왕복했으면 3×3 격자의 아래쪽 행이 1순위여야 한다."""
    segs = heatmap.extract_path(_walking_frames(passes=3, y=240), H, W)
    pmap = heatmap.accumulate_passage_map(segs, H, W)
    report = rules.analyze_report(pmap)
    assert report["findings"][0]["cell"][0] == 2


# --------------------------------------------------------------------------
# 렌더링
# --------------------------------------------------------------------------

def test_draw_path_marks_the_route(tmp_path):
    import os
    import cv2
    frame = np.zeros((H, W, 3), dtype=np.uint8)
    segs = heatmap.extract_path(_walking_frames(passes=1, y=240), H, W)
    findings = [{"cell": [2, 1], "level": "높음"}]
    out = os.path.join(tmp_path, "p.png")

    heatmap.render_hazard_boxes(frame, findings, 3, 3, out, segments=segs)
    img = cv2.imread(out)
    assert img is not None
    # 경로가 지나간 하단은 칠해지고, 경로가 없던 최상단은 검정 그대로
    assert img[240, 150].sum() > 0
    assert img[5, 150].sum() == 0


def test_render_hazard_boxes_without_segments_still_works(tmp_path):
    import os
    import cv2
    frame = np.zeros((30, 30, 3), dtype=np.uint8)
    out = os.path.join(tmp_path, "b.png")
    heatmap.render_hazard_boxes(frame, [{"cell": [0, 0], "level": "높음"}], 3, 3, out)
    assert cv2.imread(out) is not None
