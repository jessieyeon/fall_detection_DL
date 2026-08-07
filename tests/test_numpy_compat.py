"""joblib 모델이 numpy 1.x 환경에서도 로드되는지.

모델은 numpy 2.x 로 학습됐고 배포는 numpy 1.26.4 에 고정돼 있다(mediapipe 제약).
shim 없이 로드하면 ValueError 로 터지고, '내 카메라 체험'이 통째로 비활성화된다.
이 테스트가 그 조합을 고정한다.
"""

import os

import pytest

import numpy_compat


MODEL = "fall_risk_model_v5.joblib"
needs_model = pytest.mark.skipif(not os.path.isfile(MODEL),
                                 reason="모델 파일이 없는 환경(CI 최소 설치)")


@needs_model
def test_bundle_loads_with_compat():
    joblib = pytest.importorskip("joblib")
    with numpy_compat.bitgen_compat():
        bundle = joblib.load(MODEL)
    assert bundle["version"] >= 2
    assert len(bundle["features"]) > 0


@needs_model
def test_live_self_load_bundle_succeeds():
    """라우트가 '체험 가능'으로 응답하려면 이게 None 이면 안 된다."""
    pytest.importorskip("joblib")
    pytest.importorskip("sklearn")
    pytest.importorskip("pandas")
    from webservice import live_self
    live_self._BUNDLE = None
    live_self._BUNDLE_TRIED = False
    assert live_self.load_bundle() is not None


def test_compat_is_reverted_after_use():
    """shim 은 읽는 동안만 적용돼야 한다. 영구 패치는 저장을 깨뜨린다."""
    np_pickle = pytest.importorskip("numpy.random._pickle")
    before = np_pickle.__dict__.get("__bit_generator_ctor")
    with numpy_compat.bitgen_compat():
        pass
    assert np_pickle.__dict__.get("__bit_generator_ctor") is before
