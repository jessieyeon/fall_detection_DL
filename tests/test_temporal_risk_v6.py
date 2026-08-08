"""v6 스코어러 — 학습(train_v6.add_normalized)과 같은 파생값을 내는지.

학습과 서빙이 다른 값을 쓰면 모델은 **조용히** 틀린다. 예외도 안 나고 확률만
이상해져서, 시연 중에 "왜 안 잡히지"로 나타난다. 그래서 두 구현이 같은 입력에
같은 값을 내는지 직접 비교한다.
"""

import os
import sys

import pytest

pd = pytest.importorskip("pandas")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "model_training"))
from train_v6 import add_normalized                              # noqa: E402
from temporal_risk import derive_v6                              # noqa: E402


def test_derive_matches_training_definition():
    raw = {"vertical_velocity": 0.4, "horizontal_velocity": -0.1,
           "torso_n": 0.30, "body_n": 0.80, "hip_y": 0.50, "ankle_y": 0.90}
    want = add_normalized(pd.DataFrame([raw])).iloc[0]
    got = derive_v6(raw["vertical_velocity"], raw["horizontal_velocity"],
                    raw["torso_n"], raw["body_n"], raw["hip_y"], raw["ankle_y"])
    for key in ("vy_torso", "vx_torso", "hip_h", "torso_ratio"):
        assert got[key] == pytest.approx(float(want[key]), rel=1e-9), key


def test_derive_matches_training_at_clip_boundary():
    """0 나눗셈 하한도 학습과 같아야 한다. 학습만 자르고 서빙이 안 자르면
    사람이 작게 잡힌 프레임에서만 값이 튄다 — 찾기 가장 어려운 종류의 불일치다."""
    raw = {"vertical_velocity": 0.4, "horizontal_velocity": 0.1,
           "torso_n": 0.001, "body_n": 0.001, "hip_y": 0.5, "ankle_y": 0.55}
    want = add_normalized(pd.DataFrame([raw])).iloc[0]
    got = derive_v6(raw["vertical_velocity"], raw["horizontal_velocity"],
                    raw["torso_n"], raw["body_n"], raw["hip_y"], raw["ankle_y"])
    for key in ("vy_torso", "vx_torso", "hip_h", "torso_ratio"):
        assert got[key] == pytest.approx(float(want[key]), rel=1e-9), key


def test_derive_survives_zero_lengths():
    got = derive_v6(0.4, 0.1, 0.0, 0.0, 0.5, 0.5)
    assert all(abs(v) < 1e6 for v in got.values())


class _FakeModel:
    def predict_proba(self, x):
        return [[0.5, 0.5]]


def _v6_bundle():
    return {"model": _FakeModel(), "features": ["vy_torso"], "version": 6,
            "base_features": ["vy_torso", "vx_torso", "hip_h", "torso_ratio"],
            "windows": [5], "slope_cols": [], "slope_lag": 12, "fps": 25.0,
            "ewma_alpha": 0.3, "proba_ewma_alpha": 0.4}


def test_v6_scorer_requires_new_features():
    """v6 번들인데 새 값을 안 주면 조용히 틀리지 말고 바로 터져야 한다."""
    from temporal_risk import TemporalRiskScorer
    s = TemporalRiskScorer(_v6_bundle())
    with pytest.raises(ValueError):
        s.update(0.1, 0.1, 10.0, 1.0, tilt3d=10.0, aspect=0.5, shoulder_y=0.4)


def test_v6_scorer_runs_with_new_features():
    from temporal_risk import TemporalRiskScorer
    s = TemporalRiskScorer(_v6_bundle())
    p = s.update(0.1, 0.1, 10.0, 1.0, tilt3d=10.0, aspect=0.5, shoulder_y=0.4,
                 torso_n=0.3, body_n=0.8, hip_y=0.5, ankle_y=0.9)
    assert 0.0 <= p <= 1.0


def test_v5_path_still_works():
    """v6 를 추가하면서 배포 중인 v5 경로를 깨뜨리면 안 된다."""
    from temporal_risk import TemporalRiskScorer
    bundle = {"model": _FakeModel(), "features": ["tilt3d_deg"], "version": 5,
              "base_features": ["tilt3d_deg"], "windows": [5], "slope_cols": [],
              "slope_lag": 12, "fps": 25.0, "ewma_alpha": 0.3,
              "proba_ewma_alpha": 0.4, "rel_features": [], "long_alpha": 0.02}
    s = TemporalRiskScorer(bundle)
    p = s.update(0.1, 0.1, 10.0, 1.0, tilt3d=10.0, aspect=0.5, shoulder_y=0.4)
    assert 0.0 <= p <= 1.0
