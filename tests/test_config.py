import json

import pytest

import config


def write_profiles(tmp_path, data):
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


VALID = {
    "human": {"persistence": 3, "prob_threshold": 0.70,
              "tau_R": 0.85, "tau_R_strict": 0.95, "tau_lean": 0.15, "window": 8},
    "doll": {"persistence": 2, "prob_threshold": 0.60,
             "tau_R": 0.80, "tau_R_strict": 0.93, "tau_lean": 0.12, "window": 6},
}


def test_loads_named_profile(tmp_path):
    path = write_profiles(tmp_path, VALID)
    profile = config.load_profile("doll", path)
    assert profile.name == "doll"
    assert profile.persistence == 2
    assert profile.tau_R == 0.80
    assert profile.tau_R_strict == 0.93
    assert profile.tau_lean == 0.12
    assert profile.window == 6
    assert profile.prob_threshold == 0.60


def test_unknown_profile_name_raises(tmp_path):
    path = write_profiles(tmp_path, VALID)
    with pytest.raises(ValueError, match="rabbit"):
        config.load_profile("rabbit", path)


def test_missing_file_raises(tmp_path):
    with pytest.raises(ValueError, match="찾을 수 없"):
        config.load_profile("human", str(tmp_path / "nope.json"))


def test_missing_key_raises(tmp_path):
    broken = {"human": {"persistence": 3}}
    path = write_profiles(tmp_path, broken)
    with pytest.raises(ValueError, match="prob_threshold"):
        config.load_profile("human", path)


def test_tau_R_above_tau_R_strict_raises(tmp_path):
    # tau_R <= tau_R_strict 관계가 깨지면 규칙 3 이 영원히 발동하지 않거나
    # 게이트와 모순된다 (설계 문서 §6.5)
    broken = {"human": dict(VALID["human"], tau_R=0.97, tau_R_strict=0.95)}
    path = write_profiles(tmp_path, broken)
    with pytest.raises(ValueError, match="tau_R"):
        config.load_profile("human", path)


def test_shipped_profiles_json_is_valid():
    for name in ("human", "doll"):
        profile = config.load_profile(name)
        assert profile.name == name
        assert 0.0 <= profile.tau_lean <= 1.0
        assert 0.0 <= profile.tau_R <= profile.tau_R_strict <= 1.0
        assert profile.persistence >= 1
        assert profile.window >= 1


def test_malformed_json_raises(tmp_path):
    # 잘못된 JSON 파일에서 파일 경로를 포함한 ValueError 를 발생시킨다.
    path = tmp_path / "profiles.json"
    path.write_text("{invalid json", encoding="utf-8")
    with pytest.raises(ValueError, match=str(path)):
        config.load_profile("human", str(path))
