"""numpy 1.x / 2.x 사이의 joblib 모델 호환 계층.

sklearn 모델에는 난수 생성기(BitGenerator)가 함께 피클된다. numpy 2.x 와 1.x 는
이걸 저장하는 방식이 달라서, numpy 2.x 로 학습한 모델을 numpy 1.x 로 읽으면
이렇게 터진다.

    ValueError: <class 'numpy.random._pcg64.PCG64'> is not a known BitGenerator

mediapipe 0.10.14 가 numpy<2 를 요구해서 numpy 를 올릴 수 없고, 모델을 다시
학습하는 것도 과하다. 복원 함수 세 개를 감싸 차이를 흡수한다.

이 모듈은 **표준 라이브러리와 numpy 만** 쓴다. 배포 서버(mediapipe 없음)의
webservice/live_self.py 와 부스 파이프라인의 pose_source.py 가 같이 쓰기 때문이다.
pose_source 에 두면 서버가 임포트할 수 없어서 모델 로드가 통째로 실패한다.
"""

import contextlib

_BITGEN_COMPAT_CACHE = {}


def _compat_bitgen_class(cls):
    """상태를 튜플로 받아도 복원되는 BitGenerator 서브클래스.

    numpy 2.x 는 난수 생성기 상태를 `(state_dict, SeedSequence)` 튜플로 저장하는데
    numpy 1.x 의 `__setstate__` 는 dict 만 받는다. 앞의 dict 만 넘겨주면 된다
    (SeedSequence 는 재현용 메타데이터라 학습이 끝난 모델의 추론에는 쓰이지 않는다).
    """
    if cls not in _BITGEN_COMPAT_CACHE:
        class _Compat(cls):
            def __setstate__(self, state):
                if isinstance(state, tuple):
                    state = state[0]
                super().__setstate__(state)

        _Compat.__name__ = cls.__name__
        _BITGEN_COMPAT_CACHE[cls] = _Compat
    return _BITGEN_COMPAT_CACHE[cls]


@contextlib.contextmanager
def bitgen_compat():
    """모델을 읽는 동안만 numpy 복원 함수를 갈아끼운다.

      · 클래스나 인스턴스가 오면 이름 문자열로 바꿔 넘긴다
      · 상태가 튜플이면 앞의 dict 만 쓴다 (_compat_bitgen_class)

    `__randomstate_ctor` / `__generator_ctor` 까지 함께 바꾸는 이유: 두 함수는
    `bit_generator_ctor=__bit_generator_ctor` 를 **기본 인자로** 받는데, 기본 인자는
    모듈 임포트 시점에 원본 함수로 묶여버린다. 모듈 속성만 갈아끼우면 이들은 여전히
    원본을 호출해서 패치가 먹지 않는다.

    **읽는 동안만** 적용하고 반드시 되돌린다. 영구히 갈아끼우면 이번엔 저장이
    깨진다 — 피클러가 교체된 로컬 함수를 참조하려다 실패한다
    (`Can't pickle local object`). 학습 스크립트가 같은 프로세스에서 모델을 저장할
    수도 있으므로 전역 상태를 남기지 않는다.

    문자열·dict 로 저장된 기존 모델도 그대로 동작하므로 양방향 모두 안전하다.
    """
    try:
        import numpy as np
        from numpy.random import _pickle as np_pickle
    except ImportError:
        yield
        return

    saved = {name: getattr(np_pickle, name, None) for name in
             ("__bit_generator_ctor", "__randomstate_ctor", "__generator_ctor")}
    orig_bg = saved["__bit_generator_ctor"]
    if orig_bg is None:
        yield
        return

    def _name_of(x):
        if isinstance(x, str):
            return x
        return getattr(x, "__name__", None) or type(x).__name__

    def bit_generator_ctor(bit_generator="MT19937"):
        name = _name_of(bit_generator)
        cls = np_pickle.BitGenerators.get(name)
        return _compat_bitgen_class(cls)() if cls is not None else orig_bg(name)

    def randomstate_ctor(bit_generator_name="MT19937",
                         bit_generator_ctor=bit_generator_ctor):
        return np.random.RandomState(bit_generator_ctor(bit_generator_name))

    def generator_ctor(bit_generator_name="MT19937",
                       bit_generator_ctor=bit_generator_ctor):
        return np.random.Generator(bit_generator_ctor(bit_generator_name))

    np_pickle.__bit_generator_ctor = bit_generator_ctor
    np_pickle.__randomstate_ctor = randomstate_ctor
    np_pickle.__generator_ctor = generator_ctor
    try:
        yield
    finally:
        for name, fn in saved.items():
            if fn is not None:
                setattr(np_pickle, name, fn)
