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
