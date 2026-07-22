import math

import pytest

import tiles


def make_landmarks(shoulder, hip):
    """MediaPipe Pose 랜드마크 33개짜리 리스트를 만들되 어깨(11,12)와
    엉덩이(23,24)만 채운다. 나머지는 이 모듈이 읽지 않는다."""
    lm = [(0.0, 0.0, 0.0)] * 33
    lm[tiles.L_SHOULDER] = shoulder
    lm[tiles.R_SHOULDER] = shoulder
    lm[tiles.L_HIP] = hip
    lm[tiles.R_HIP] = hip
    return lm


def test_upright_torso_has_zero_lean_ratio():
    # 어깨가 엉덩이 바로 위(이미지 y는 아래가 +)
    lm = make_landmarks(shoulder=(100.0, 100.0, 0.0), hip=(100.0, 200.0, 0.0))
    _, lean_ratio = tiles.lean_from_landmarks(lm)
    assert lean_ratio == pytest.approx(0.0, abs=1e-6)


def test_leaning_right_is_90_degrees():
    # 어깨가 엉덩이보다 오른쪽(+x)
    lm = make_landmarks(shoulder=(200.0, 100.0, 0.0), hip=(100.0, 200.0, 0.0))
    direction, lean_ratio = tiles.lean_from_landmarks(lm)
    assert direction == pytest.approx(90.0)
    assert lean_ratio == pytest.approx(math.sqrt(0.5))


def test_leaning_left_is_270_degrees():
    lm = make_landmarks(shoulder=(0.0, 100.0, 0.0), hip=(100.0, 200.0, 0.0))
    direction, _ = tiles.lean_from_landmarks(lm)
    assert direction == pytest.approx(270.0)


def test_leaning_away_from_camera_is_0_degrees():
    # z 가 커질수록 카메라에서 멀어진다
    lm = make_landmarks(shoulder=(100.0, 100.0, 100.0), hip=(100.0, 200.0, 0.0))
    direction, _ = tiles.lean_from_landmarks(lm)
    assert direction == pytest.approx(0.0)


def test_leaning_toward_camera_is_180_degrees():
    lm = make_landmarks(shoulder=(100.0, 100.0, -100.0), hip=(100.0, 200.0, 0.0))
    direction, _ = tiles.lean_from_landmarks(lm)
    assert direction == pytest.approx(180.0)


def test_diagonal_landmarks_give_45_degrees():
    # dx, dz 둘 다 0이 아닌 진짜 대각 사례 - 1장/3장 선택의 헤드라인 기능이
    # 실제로 어깨/엉덩이 랜드마크에서 끝까지 나오는지 확인한다
    lm = make_landmarks(shoulder=(200.0, 100.0, 100.0), hip=(100.0, 200.0, 0.0))
    direction, _ = tiles.lean_from_landmarks(lm)
    assert direction == pytest.approx(45.0)


def test_diagonal_landmarks_give_225_degrees_in_mirrored_quadrant():
    # 반대쪽 사분면(좌 + 카메라 쪽)도 동일하게 확인한다
    lm = make_landmarks(shoulder=(0.0, 100.0, -100.0), hip=(100.0, 200.0, 0.0))
    direction, _ = tiles.lean_from_landmarks(lm)
    assert direction == pytest.approx(225.0)


def test_camera_yaw_rotates_the_direction():
    # 카메라가 격자 대비 90도 돌아가 있으면 "이미지상 우측"이 격자상 0도가 된다
    lm = make_landmarks(shoulder=(200.0, 100.0, 0.0), hip=(100.0, 200.0, 0.0))
    direction, _ = tiles.lean_from_landmarks(lm, camera_yaw_deg=90.0)
    assert direction == pytest.approx(0.0)


def test_fully_horizontal_torso_has_lean_ratio_one():
    # 어깨와 엉덩이의 y가 같으면 완전히 누운 상태
    lm = make_landmarks(shoulder=(200.0, 100.0, 0.0), hip=(100.0, 100.0, 0.0))
    _, lean_ratio = tiles.lean_from_landmarks(lm)
    assert lean_ratio == pytest.approx(1.0)


def test_degenerate_zero_length_torso_does_not_divide_by_zero():
    lm = make_landmarks(shoulder=(100.0, 100.0, 0.0), hip=(100.0, 100.0, 0.0))
    direction, lean_ratio = tiles.lean_from_landmarks(lm)
    assert direction == 0.0
    assert lean_ratio == 0.0


def test_circular_mean_wraps_around_zero():
    # 산술평균이면 180도가 나온다. 이 함수가 존재하는 이유가 정확히 이것이다.
    mean_direction, _, _ = tiles.resolve_direction([(350.0, 0.5), (10.0, 0.5)])
    assert mean_direction == pytest.approx(0.0, abs=1e-6)


def test_identical_directions_give_R_of_one():
    window = [(90.0, 0.4)] * 5
    mean_direction, R, mean_lean = tiles.resolve_direction(window)
    assert mean_direction == pytest.approx(90.0)
    assert R == pytest.approx(1.0)
    assert mean_lean == pytest.approx(0.4)


def test_opposite_directions_give_R_of_zero():
    _, R, _ = tiles.resolve_direction([(0.0, 0.5), (180.0, 0.5)])
    assert R == pytest.approx(0.0, abs=1e-9)


def test_scattered_directions_lower_R():
    tight = [(90.0, 0.5), (92.0, 0.5), (88.0, 0.5)]
    loose = [(90.0, 0.5), (150.0, 0.5), (30.0, 0.5)]
    _, tight_R, _ = tiles.resolve_direction(tight)
    _, loose_R, _ = tiles.resolve_direction(loose)
    assert tight_R > loose_R


def test_mean_lean_ratio_is_the_arithmetic_mean():
    _, _, mean_lean = tiles.resolve_direction([(90.0, 0.2), (90.0, 0.6)])
    assert mean_lean == pytest.approx(0.4)


def test_empty_window_returns_zeros():
    assert tiles.resolve_direction([]) == (0.0, 0.0, 0.0)


# 2x2 격자에서 쓰는 기본 인자. 게이트는 통과하되 규칙 3(1장)은 발동하지 않는 값.
GRID = dict(rows=2, cols=2, tau_R=0.85, tau_R_strict=0.95, tau_lean=0.15)


def pick(direction_deg, R=0.90, lean_ratio=0.40, **overrides):
    kwargs = dict(GRID)
    kwargs.update(overrides)
    return tiles.select_tiles(direction_deg, R, lean_ratio, **kwargs)


# --- 규칙 1: 정방향은 행 또는 열 전체 (2장) ---

def test_cardinal_far_selects_top_row():
    assert pick(0.0) == {0, 1}


def test_cardinal_right_selects_right_column():
    assert pick(90.0) == {1, 3}


def test_cardinal_near_selects_bottom_row():
    assert pick(180.0) == {2, 3}


def test_cardinal_left_selects_left_column():
    assert pick(270.0) == {0, 2}


# --- 규칙 2: 대각은 반대편 모서리 제외 (3장) ---

def test_diagonal_far_right_excludes_near_left_corner():
    assert pick(45.0) == {0, 1, 3}


def test_diagonal_near_right_excludes_far_left_corner():
    assert pick(135.0) == {1, 2, 3}


def test_diagonal_near_left_excludes_far_right_corner():
    assert pick(225.0) == {0, 2, 3}


def test_diagonal_far_left_excludes_near_right_corner():
    assert pick(315.0) == {0, 1, 2}


# --- 규칙 3: 대각 정밀은 모서리 한 장 ---

def test_precise_diagonal_selects_single_corner():
    assert pick(45.0, R=0.97) == {1}
    assert pick(135.0, R=0.97) == {3}
    assert pick(225.0, R=0.97) == {2}
    assert pick(315.0, R=0.97) == {0}


def test_precise_diagonal_needs_both_angle_and_agreement():
    # 각도는 맞지만 R 이 tau_R_strict 미만이면 3장
    assert pick(45.0, R=0.94) == {0, 1, 3}
    # R 은 충분하지만 대각 중심에서 10도를 벗어나면 3장
    assert pick(34.9, R=0.99) == {0, 1, 3}


def test_precise_diagonal_tolerance_boundary():
    assert pick(35.0, R=0.99) == {1}      # 정확히 10도 — 포함
    assert pick(55.0, R=0.99) == {1}
    assert pick(34.9, R=0.99) == {0, 1, 3}
    assert pick(55.1, R=0.99) == {0, 1, 3}


def test_cardinal_never_narrows_to_one_tile():
    # 2x2 에서 "우측"만으로는 앞뒤 성분을 알 수 없으므로 열 전체를 덮어야 한다
    assert pick(90.0, R=1.0) == {1, 3}
    assert pick(0.0, R=1.0) == {0, 1}


# --- 게이트: 규칙보다 우선한다 ---

def test_low_agreement_fires_all_tiles():
    assert pick(90.0, R=0.50) == {0, 1, 2, 3}


def test_low_lean_ratio_fires_all_tiles():
    assert pick(90.0, lean_ratio=0.05) == {0, 1, 2, 3}


def test_gate_beats_precise_diagonal_rule():
    # 각도와 R 이 규칙 3을 만족해도 수직 붕괴면 4장이다
    assert pick(45.0, R=0.99, lean_ratio=0.05) == {0, 1, 2, 3}


# --- 구간 경계와 되감김 ---

def test_sector_boundary_at_22_5_degrees():
    assert pick(22.4) == {0, 1}          # 정방향(먼 쪽)
    assert pick(22.6) == {0, 1, 3}       # 대각


def test_wraps_around_360():
    assert pick(359.9) == {0, 1}
    assert pick(0.1) == {0, 1}
    assert pick(360.0) == {0, 1}


# --- 불변식 ---

@pytest.mark.parametrize("direction", [d * 3.0 for d in range(120)])
@pytest.mark.parametrize("R", [0.5, 0.86, 0.99])
@pytest.mark.parametrize("lean_ratio", [0.05, 0.4])
def test_result_size_is_always_one_to_four(direction, R, lean_ratio):
    result = pick(direction, R=R, lean_ratio=lean_ratio)
    assert 1 <= len(result) <= 4
    assert result <= {0, 1, 2, 3}
