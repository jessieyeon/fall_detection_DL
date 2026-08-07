"""v6 정규화 파생 특징 — 학습과 서빙이 같은 값을 내야 한다.

여기서 검증하는 것은 '카메라가 멀어져도 값이 안 변한다'는 성질 자체다.
이게 깨지면 정규화를 한 의미가 없다.
"""

import os
import sys

import pytest

pd = pytest.importorskip("pandas")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "model_training"))
from train_v6 import add_normalized                              # noqa: E402


def _row(scale):
    """카메라 거리만 다른 같은 동작. scale=0.5 면 사람이 절반 크기로 보인다."""
    return {"vertical_velocity": 0.4 * scale, "horizontal_velocity": 0.1 * scale,
            "torso_n": 0.30 * scale, "body_n": 0.80 * scale,
            "hip_y": 0.50, "ankle_y": 0.50 + 0.40 * scale}


def test_speed_is_camera_distance_invariant():
    df = add_normalized(pd.DataFrame([_row(1.0), _row(0.5)]))
    assert df["vy_torso"].iloc[0] == pytest.approx(df["vy_torso"].iloc[1], rel=1e-6)
    assert df["vx_torso"].iloc[0] == pytest.approx(df["vx_torso"].iloc[1], rel=1e-6)


def test_hip_height_is_camera_distance_invariant():
    df = add_normalized(pd.DataFrame([_row(1.0), _row(0.5)]))
    assert df["hip_h"].iloc[0] == pytest.approx(df["hip_h"].iloc[1], rel=1e-6)


def test_standing_hip_is_higher_than_lying():
    """서 있으면 엉덩이가 발목보다 한참 위, 누우면 거의 같은 높이."""
    standing = {"vertical_velocity": 0, "horizontal_velocity": 0,
                "torso_n": 0.3, "body_n": 0.8, "hip_y": 0.5, "ankle_y": 0.9}
    lying = {"vertical_velocity": 0, "horizontal_velocity": 0,
             "torso_n": 0.3, "body_n": 0.25, "hip_y": 0.86, "ankle_y": 0.88}
    df = add_normalized(pd.DataFrame([standing, lying]))
    assert df["hip_h"].iloc[0] > 0.4
    assert df["hip_h"].iloc[1] < 0.15


def test_zero_torso_does_not_divide_by_zero():
    """사람이 아주 작게 잡히거나 랜드마크가 겹친 프레임에서도 터지지 않는다."""
    bad = {"vertical_velocity": 0.4, "horizontal_velocity": 0.1,
           "torso_n": 0.0, "body_n": 0.0, "hip_y": 0.5, "ankle_y": 0.5}
    df = add_normalized(pd.DataFrame([bad]))
    assert df["vy_torso"].notna().all()
    assert abs(df["vy_torso"].iloc[0]) < 1e6
