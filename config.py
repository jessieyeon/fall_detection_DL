"""판정 파라미터 프로파일 로드.

인형은 사람보다 약 2.4배 빠르게 쓰러지므로(역진자 각속도가 몸 길이의 제곱근에
반비례) persistence 와 임계값을 대상별로 분리한다.

tau_R, tau_R_strict, tau_lean 은 물리 상수가 아니라 연출값이다. 리허설 로그의
분포를 보고 확정한다 (설계 문서 §10.3). 코드 상수로 두면 시연 당일에 잘못된
값이 남으므로 반드시 이 파일에 둔다.
"""

import json
import os
from dataclasses import dataclass

PROFILE_FILE = "profiles.json"
DEFAULT_PROFILE = "human"

_REQUIRED_KEYS = (
    "persistence",
    "prob_threshold",
    "tau_R",
    "tau_R_strict",
    "tau_lean",
    "window",
)


@dataclass(frozen=True)
class Profile:
    name: str
    persistence: int
    prob_threshold: float
    tau_R: float
    tau_R_strict: float
    tau_lean: float
    window: int


def load_profile(name, path=PROFILE_FILE):
    if not os.path.isfile(path):
        raise ValueError(f"프로파일 파일을 찾을 수 없습니다: {path}")

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if name not in data:
        available = ", ".join(sorted(data)) or "(없음)"
        raise ValueError(f"프로파일 '{name}' 이 없습니다. 사용 가능: {available}")

    entry = data[name]
    missing = [key for key in _REQUIRED_KEYS if key not in entry]
    if missing:
        raise ValueError(f"프로파일 '{name}' 에 항목이 없습니다: {', '.join(missing)}")

    profile = Profile(
        name=name,
        persistence=int(entry["persistence"]),
        prob_threshold=float(entry["prob_threshold"]),
        tau_R=float(entry["tau_R"]),
        tau_R_strict=float(entry["tau_R_strict"]),
        tau_lean=float(entry["tau_lean"]),
        window=int(entry["window"]),
    )

    if profile.tau_R > profile.tau_R_strict:
        raise ValueError(
            f"프로파일 '{name}': tau_R({profile.tau_R}) 는 "
            f"tau_R_strict({profile.tau_R_strict}) 이하여야 합니다."
        )

    return profile
