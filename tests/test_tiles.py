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
