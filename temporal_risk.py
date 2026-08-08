"""
v2/v3/v4 모델용 실시간 시간 특징 계산기 + 위험도 스코어러.

model_training/train_classifier_v2.py(v2/v3) 및 train_classifier_v4.py(v4) 의
add_temporal_features() 와 완전히 동일한 값을 프레임 단위 스트리밍으로 계산한다
(학습/서빙 일치). pandas rolling(std ddof=1, min_periods=1) / ewm(adjust=True) 의
정의를 그대로 재현한다.

v4는 기본 특징이 7개로 확장됨:
  vy, vx, tilt2d, tilt_vel  (v2/v3와 동일)
  + tilt3d_deg   : MediaPipe world landmarks 기반 3D 몸통 각도 (전/후방 낙상 대응)
  + aspect_ratio : 인체 바운딩 박스 폭/높이 (누움 판정)
  + shoulder_y   : 정규화 어깨 높이 (하강 판정)

사용법:
    scorer = TemporalRiskScorer(bundle)      # joblib.load("fall_risk_model_v4.joblib")
    proba = scorer.update(vy, vx, tilt, tilt_vel,
                          tilt3d=..., aspect=..., shoulder_y=...)   # v4
    proba = scorer.update(vy, vx, tilt, tilt_vel)                   # v2/v3
    scorer.reset()                            # 포즈 소실 시 히스토리 무효화
"""
import math
from collections import deque

import numpy as np
import pandas as pd

BASE_V2 = ["vertical_velocity", "horizontal_velocity", "tilt_angle_deg", "tilt_angular_velocity"]
BASE_V4 = BASE_V2 + ["tilt3d_deg", "aspect_ratio", "shoulder_y"]
SLOPE_COLS_V2 = ("tilt_angle_deg", "vertical_velocity")
SLOPE_COLS_V4 = ("tilt_angle_deg", "vertical_velocity", "tilt3d_deg", "aspect_ratio", "shoulder_y")

# v5: 도메인 불변 상대 특징. 각 값에서 '그 영상 자신의 장기 기준선'(인과적 EWMA)을 뺀 편차.
# 카메라 높이·거리·화각이 달라도 "평소 자세 대비 얼마나 벗어났나"는 보존된다.
# (DAFD, IEEE TNSRE 2021 의 domain-adaptive 아이디어를 배포 가능한 형태로 구현)
REL_SRC_V5 = ["tilt3d_deg", "aspect_ratio", "shoulder_y", "tilt_angle_deg"]

# v6: 카메라 거리 불변 파생 특징. 카메라가 멀어지면 사람이 작게 잡혀 같은 낙상이
# 느린 속도로 기록되는데, 몸통 길이로 나누면 그 의존이 사라진다.
BASE_V6 = BASE_V4 + ["vy_torso", "vx_torso", "hip_h", "torso_ratio"]

# 0 나눗셈 하한. model_training/train_v6.py 의 MIN_TORSO/MIN_BODY 와 **같아야 한다**.
MIN_TORSO, MIN_BODY = 0.02, 0.05


def derive_v6(vy, vx, torso_n, body_n, hip_y, ankle_y):
    """train_v6.add_normalized 의 한 행짜리 판. 두 구현은 반드시 같은 값을 내야 한다.

    학습과 서빙이 갈라지면 예외 없이 확률만 이상해져서 찾기가 매우 어렵다.
    tests/test_temporal_risk_v6.py 가 두 구현을 직접 비교해 고정한다.
    """
    t = max(torso_n, MIN_TORSO)
    b = max(body_n, MIN_BODY)
    return {"vy_torso": vy / t, "vx_torso": vx / t,
            "hip_h": (ankle_y - hip_y) / b, "torso_ratio": t / b}


class _Ewma:
    """pandas Series.ewm(alpha=a, adjust=True).mean() 의 스트리밍 재현."""

    def __init__(self, alpha):
        self.alpha = alpha
        self.num = 0.0
        self.den = 0.0

    def update(self, x):
        r = 1.0 - self.alpha
        self.num = x + r * self.num
        self.den = 1.0 + r * self.den
        return self.num / self.den

    def reset(self):
        self.num = self.den = 0.0


class TemporalRiskScorer:
    def __init__(self, bundle):
        self.model = bundle["model"]
        self.features = bundle["features"]
        self.windows = tuple(bundle["windows"])
        self.slope_lag = bundle["slope_lag"]
        self.fps = bundle["fps"]
        self.version = bundle.get("version", 2)
        self.proba_ewma = _Ewma(bundle["proba_ewma_alpha"])
        self.ewma_alpha = bundle["ewma_alpha"]
        if self.version >= 6:
            self.base = bundle["base_features"]              # 7 raw + 4 정규화
            self.slope_cols = tuple(bundle["slope_cols"])
            self.rel_src = []                                # v6 는 상대특징을 쓰지 않는다
            self.long_alpha = bundle.get("long_alpha", 0.02)
        elif self.version == 5:
            self.base = bundle["base_features"]              # 7 raw + 4 rel
            self.slope_cols = tuple(bundle["slope_cols"])
            self.rel_src = bundle["rel_features"]
            self.long_alpha = bundle["long_alpha"]
        else:
            self.base = BASE_V4 if self.version >= 4 else BASE_V2
            self.slope_cols = SLOPE_COLS_V4 if self.version >= 4 else SLOPE_COLS_V2
            self.rel_src = []
        self.reset()

    def reset(self):
        maxw = max(max(self.windows), self.slope_lag + 1)
        self.hist = {c: deque(maxlen=maxw) for c in self.base + ["speed_mag"]}
        self.ewmas = {c: _Ewma(self.ewma_alpha) for c in self.base}
        self.long_ewmas = {c: _Ewma(self.long_alpha) for c in self.rel_src} if self.rel_src else {}
        self.prev = {}
        self.proba_ewma.reset()

    def _roll_stats(self, col, w):
        vals = list(self.hist[col])[-w:]
        m = sum(vals) / len(vals)
        if len(vals) > 1:
            s = math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1))  # ddof=1
        else:
            s = 0.0
        return m, s, max(vals) - min(vals)

    def update(self, vy, vx, tilt, tilt_vel,
               tilt3d=None, aspect=None, shoulder_y=None,
               torso_n=None, body_n=None, hip_y=None, ankle_y=None):
        """한 프레임의 기본 특징을 받아 평활화된 낙상 위험 확률을 반환."""
        base = {"vertical_velocity": vy, "horizontal_velocity": vx,
                "tilt_angle_deg": tilt, "tilt_angular_velocity": tilt_vel}
        if self.version >= 4:
            if tilt3d is None or aspect is None or shoulder_y is None:
                raise ValueError("v4 모델은 tilt3d/aspect/shoulder_y 가 필요합니다")
            base.update({"tilt3d_deg": tilt3d, "aspect_ratio": aspect,
                         "shoulder_y": shoulder_y})
        if self.version >= 6:
            if None in (torso_n, body_n, hip_y, ankle_y):
                raise ValueError(
                    "v6 모델은 torso_n/body_n/hip_y/ankle_y 가 필요합니다")
            base.update(derive_v6(vy, vx, torso_n, body_n, hip_y, ankle_y))
        if self.version == 5:
            # 상대 특징을 먼저 만든다 (학습 시 add_relative 가 시간특징보다 앞서므로 순서 일치)
            for c in self.rel_src:
                base[f"{c}_rel"] = base[c] - self.long_ewmas[c].update(base[c])
        f = dict(base)
        # v6 는 속도 파생도 정규화 속도로 만든다 (train_v6.add_temporal_v6 와 일치).
        # 원시 속도로 만들면 그 값만 카메라 거리에 다시 끌려간다.
        if self.version >= 6:
            f["speed_mag"] = math.hypot(base["vy_torso"], base["vx_torso"])
            f["vert_accel"] = (base["vy_torso"]
                               - self.prev.get("vy_torso", base["vy_torso"])) * self.fps
            f["hip_h_vel"] = (base["hip_h"]
                              - self.prev.get("hip_h", base["hip_h"])) * self.fps
        else:
            f["speed_mag"] = math.hypot(vy, vx)
            f["vert_accel"] = (vy - self.prev.get("vertical_velocity", vy)) * self.fps
        f["tilt_accel"] = (tilt_vel - self.prev.get("tilt_angular_velocity", tilt_vel)) * self.fps
        if self.version >= 4:
            f["tilt3d_vel"] = (tilt3d - self.prev.get("tilt3d_deg", tilt3d)) * self.fps
            f["aspect_vel"] = (aspect - self.prev.get("aspect_ratio", aspect)) * self.fps
            f["shoulder_vel"] = (shoulder_y - self.prev.get("shoulder_y", shoulder_y)) * self.fps

        for c in self.base + ["speed_mag"]:
            self.hist[c].append(f[c])

        for w in self.windows:
            for c in self.base + ["speed_mag"]:
                m, s, r = self._roll_stats(c, w)
                f[f"{c}_m{w}"] = m
                f[f"{c}_s{w}"] = s
                f[f"{c}_r{w}"] = r

        for c in self.slope_cols:
            h = self.hist[c]
            if len(h) > self.slope_lag:
                f[f"{c}_slope"] = (f[c] - h[-1 - self.slope_lag]) / (self.slope_lag / self.fps)
            else:
                f[f"{c}_slope"] = 0.0

        for c in self.base:
            f[f"{c}_ewma"] = self.ewmas[c].update(f[c])

        self.prev = base
        x = pd.DataFrame([[f[name] for name in self.features]], columns=self.features)
        proba = float(self.model.predict_proba(x)[0][1])
        return self.proba_ewma.update(proba)
