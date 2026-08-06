"""카메라/영상 입력 어댑터.

프레임을 읽어 포즈를 추정하고, 학습된 분류기로 낙상 위험도를 계산하고,
몸통 기울기에서 낙상 방향을 뽑아 PoseFrame 으로 내놓는다.

모델 입력 특징 [vy, vx, tilt, tilt_vel] 의 계산 방식은 main.py 에 있던 것을
그대로 옮긴 것이다. model_training/extract_features.py 와 반드시 일치해야 하며,
바꾸면 학습/서빙 불일치가 발생한다.

v4 모델은 여기에 3개 특징이 추가된다 (tilt3d_deg, aspect_ratio, shoulder_y).
정의는 model_training/extract_features_v4.py 와 일치해야 한다.
"""

import math
import contextlib
import os
from collections import deque
from dataclasses import dataclass
from time import sleep, time

import cv2
import joblib
import mediapipe as mp

import tiles

SMOOTHING_WINDOW = 3        # 랜드마크 지터를 줄이려고 평균낼 프레임 수
VELOCITY_THRESHOLD = 1.2    # 모델 파일이 없을 때만 쓰는 옛 단일 임계값

L_SHOULDER, R_SHOULDER = 11, 12
L_HIP, R_HIP = 23, 24


@dataclass
class PoseFrame:
    image: "np.ndarray"
    landmarks: list
    timestamp: float
    risk_score: float
    is_risky: bool
    direction_deg: float
    lean_ratio: float
    face_name: str


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
def _numpy_bitgen_compat():
    """numpy 버전이 다른 환경에서 저장한 모델도 읽을 수 있게 한다.

    sklearn 모델에는 난수 생성기(BitGenerator)가 함께 피클된다. numpy 2.x 와 1.x 는
    이걸 저장하는 방식이 달라서, numpy 2.x 로 학습한 모델을 numpy 1.x 로 읽으면
    이렇게 터진다.

        ValueError: <class 'numpy.random._pcg64.PCG64'> is not a known BitGenerator

    mediapipe 0.10.14 가 numpy<2 를 요구해서 numpy 를 올릴 수 없고, 모델을 다시
    학습하는 것도 과하다. 복원 함수 세 개를 감싸 차이를 흡수한다.

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


def load_risk_model(path="fall_risk_model.joblib", v2_path="fall_risk_model_v2.joblib",
                    v3_path="fall_risk_model_v3.joblib", v4_path="fall_risk_model_v4.joblib",
                    v5_path="fall_risk_model_v5.joblib"):
    # 최신 버전 우선: v5(도메인불변+의사라벨) > v4(3D) > v3 > v2 > v1 > 속도 임계값
    for p, ver in ((v5_path, "v5"), (v4_path, "v4"), (v3_path, "v3"), (v2_path, "v2")):
        if not os.path.isfile(p):
            continue
        try:
            with _numpy_bitgen_compat():
                bundle = joblib.load(p)
        except Exception as exc:      # noqa: BLE001 - 한 버전이 깨져도 다음 걸로 간다
            # 모델 하나를 못 읽는다고 파이프라인 전체가 죽으면 안 된다.
            print(f"경고: {p} 를 읽을 수 없어 건너뜁니다 ({type(exc).__name__}: {exc})")
            continue
        print(f"낙상 위험 모델 {ver} 로드됨 (threshold={bundle['prob_threshold']}, "
              f"persistence={bundle['persistence']} 값은 참고용이며, "
              "실제로는 프로파일(profiles.json) 값으로 덮어써서 사용합니다)")
        return bundle
    if not os.path.isfile(path):
        print(f"경고: {path} 가 없습니다 - 단일 수직속도 임계값"
              f"({VELOCITY_THRESHOLD})으로 대체합니다.")
        return None
    try:
        with _numpy_bitgen_compat():
            bundle = joblib.load(path)
    except Exception as exc:          # noqa: BLE001
        print(f"경고: {path} 를 읽을 수 없습니다 ({type(exc).__name__}: {exc}) - "
              f"단일 수직속도 임계값({VELOCITY_THRESHOLD})으로 대체합니다.")
        return None
    print(f"낙상 위험 모델 로드됨 (번들에 저장된 threshold={bundle['prob_threshold']}, "
          f"persistence={bundle['persistence']} 값은 참고용이며, "
          "실제로는 프로파일(profiles.json) 값으로 덮어써서 사용합니다)")
    return bundle


def _midpoint(landmarks, left_index, right_index):
    left = landmarks[left_index]
    right = landmarks[right_index]
    return ((left[0] + right[0]) / 2.0, (left[1] + right[1]) / 2.0)


def torso_points(landmarks):
    """model_training/extract_features.py 와 동일한 정의를 유지할 것."""
    return (_midpoint(landmarks, L_SHOULDER, R_SHOULDER),
            _midpoint(landmarks, L_HIP, R_HIP))


def tilt_angle_deg(shoulder_c, hip_c):
    """모델 입력 특징. 부호를 버리는 것이 원래 정의이므로 바꾸지 말 것."""
    dx = hip_c[0] - shoulder_c[0]
    dy = hip_c[1] - shoulder_c[1]
    return math.degrees(math.atan2(abs(dx), abs(dy) + 1e-6))


def torso_center_xy(shoulder_c, hip_c):
    return ((shoulder_c[0] + hip_c[0]) / 2.0, (shoulder_c[1] + hip_c[1]) / 2.0)


class PoseSource:
    def __init__(self, video_source, model_bundle, prob_threshold,
                 tile_grid=None, face_every=0, face_recognizer=None,
                 pause_check=None):
        self.video_source = video_source
        # 매 프레임 호출되는 콜백. True 면 카메라를 놓고 대기한다(frames() 참고).
        self.pause_check = pause_check
        self.model_bundle = model_bundle
        self.prob_threshold = prob_threshold
        self.tile_grid = tile_grid
        self.face_every = face_every
        self.face_recognizer = face_recognizer
        self.camera_yaw_deg = tile_grid["camera_yaw_deg"] if tile_grid else 0.0

        self._pose = mp.solutions.pose.Pose(
            static_image_mode=False, min_detection_confidence=0.7, model_complexity=1)
        self._video = cv2.VideoCapture(video_source)
        if not self._video.isOpened():
            # 여기서 확인하지 않으면 frames() 의 while self._video.isOpened() 가
            # 그냥 프레임을 0개 내놓고 main() 이 조용히 0으로 끝난다.
            # "영상 경로를 잘못 입력함"이 "정상 실행되어 아무것도 못 찾음"처럼
            # 보이면 안 된다.
            raise ValueError(f"영상/카메라 소스를 열 수 없습니다: {video_source!r}")

        # 녹화 파일은 face_recognition 때문에 원본 프레임레이트보다 느리게 처리되므로
        # 벽시계 시간이 영상 내 시간과 어긋난다. 파일이면 파일 자체의 fps 로 만든
        # 가상 시계를 쓴다. 웹캠이나 네트워크 스트림은 실시간이므로 벽시계가 맞다.
        self._is_file = isinstance(video_source, str) and os.path.isfile(video_source)
        if self._is_file:
            fps = self._video.get(cv2.CAP_PROP_FPS)
            self._source_fps = fps if fps and fps > 0 else 30.0
            self._clock = 0.0

        self._vy_hist = deque(maxlen=SMOOTHING_WINDOW)
        self._vx_hist = deque(maxlen=SMOOTHING_WINDOW)
        self._prev_center = None
        self._prev_tilt = None
        self._prev_time = None
        self._frame_index = 0
        self._face_name = "unknown"

        # v2 번들이면 시간 특징 스코어러를 만든다 (학습/서빙 일치는 temporal_risk.py 가 보장)
        self._v2_scorer = None
        self._scorer_version = 1
        if model_bundle is not None and model_bundle.get("version", 1) >= 2:
            from temporal_risk import TemporalRiskScorer
            self._v2_scorer = TemporalRiskScorer(model_bundle)
            self._scorer_version = model_bundle.get("version", 2)

    def _detect_pose(self, frame):
        """(그려진 이미지, 픽셀 랜드마크, v4 추가특징) 을 돌려준다.
        추가특징은 model_training/extract_features_v4.py 의 정의와 반드시 일치해야 한다."""
        drawn = frame.copy()
        results = self._pose.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        if not results.pose_landmarks:
            return drawn, None, None

        height, width, _ = frame.shape
        lms = results.pose_landmarks.landmark
        landmarks = [
            (int(lm.x * width), int(lm.y * height), lm.z * width)
            for lm in lms
        ]
        for start, end in mp.solutions.pose.POSE_CONNECTIONS:
            cv2.line(drawn,
                     (landmarks[start][0], landmarks[start][1]),
                     (landmarks[end][0], landmarks[end][1]), (0, 255, 0), 3)

        # --- v4 추가 특징 ---
        xs = [p.x for p in lms]
        ys = [p.y for p in lms]
        aspect = ((max(xs) - min(xs)) * width) / (((max(ys) - min(ys)) * height) + 1e-6)
        shoulder_y = (lms[L_SHOULDER].y + lms[R_SHOULDER].y) / 2.0
        # 3D 몸통 각도: world landmarks 는 미터 단위 체중심 좌표계라 카메라 축 방향
        # (전/후방) 기울기도 잡힌다. 2D tilt 는 이 성분을 전혀 못 본다.
        tilt3d = None
        if results.pose_world_landmarks:
            wl = results.pose_world_landmarks.landmark
            dx = (wl[L_HIP].x + wl[R_HIP].x) / 2 - (wl[L_SHOULDER].x + wl[R_SHOULDER].x) / 2
            dy = (wl[L_HIP].y + wl[R_HIP].y) / 2 - (wl[L_SHOULDER].y + wl[R_SHOULDER].y) / 2
            dz = (wl[L_HIP].z + wl[R_HIP].z) / 2 - (wl[L_SHOULDER].z + wl[R_SHOULDER].z) / 2
            tilt3d = math.degrees(math.atan2(math.hypot(dx, dz), abs(dy) + 1e-9))
        extra = {"aspect": aspect, "shoulder_y": shoulder_y, "tilt3d": tilt3d}
        return drawn, landmarks, extra

    def _reset_history(self):
        """추적을 놓쳤을 때 오래된 운동 정보가 다음 낙상에 섞이지 않게 비운다."""
        self._vy_hist.clear()
        self._vx_hist.clear()
        self._prev_center = None
        self._prev_tilt = None
        self._prev_time = None
        if self._v2_scorer is not None:
            self._v2_scorer.reset()

    def _now(self):
        if self._is_file:
            self._clock += 1.0 / self._source_fps
            return self._clock
        return time()

    def _maybe_recognize_face(self, frame):
        if self.face_recognizer is None or self.face_every <= 0:
            return self._face_name
        if self._frame_index % self.face_every != 0:
            return self._face_name
        name = self.face_recognizer.recognize_face(frame)
        if name is not None:
            self._face_name = name
        return self._face_name

    def frames(self):
        while True:
            # 카메라를 잠시 놓아달라는 요청이 오면 장치를 실제로 해제한다.
            # 프레임만 버리고 캡처를 유지하면 카메라는 계속 점유된 상태라(아이폰이면
            # 계속 '사용 중'), 사용자가 기대하는 '연결 끊기'가 아니다.
            if self.pause_check is not None and self.pause_check():
                if self._video is not None:
                    self._video.release()
                    self._video = None
                    self._reset_history()
                    print("[카메라] 연결을 끊었습니다. 다시 연결하기 전까지 대기합니다.")
                sleep(0.3)
                continue

            if self._video is None:
                self._video = cv2.VideoCapture(self.video_source)
                if not self._video.isOpened():
                    # 다른 앱이 아직 장치를 붙들고 있을 수 있다 — 잠시 뒤 재시도.
                    self._video.release()
                    self._video = None
                    sleep(0.5)
                    continue
                self._reset_history()      # 끊긴 동안의 낡은 속도 이력은 버린다
                self._prev_time = None
                print("[카메라] 다시 연결했습니다.")

            if not self._video.isOpened():
                break
            ok, frame = self._video.read()
            if not ok:
                break

            self._frame_index += 1
            height, width, _ = frame.shape
            image, landmarks, extra = self._detect_pose(frame)
            face_name = self._maybe_recognize_face(frame)
            now = self._now()

            if landmarks is None:
                self._reset_history()
                yield PoseFrame(image=image, landmarks=None, timestamp=now,
                                risk_score=0.0, is_risky=False,
                                direction_deg=None, lean_ratio=None,
                                face_name=face_name)
                continue

            shoulder_c, hip_c = torso_points(landmarks)
            center = torso_center_xy(shoulder_c, hip_c)
            tilt = tilt_angle_deg(shoulder_c, hip_c)

            vy = vx = tilt_vel = 0.0
            if self._prev_center is not None and self._prev_time is not None:
                dt = now - self._prev_time
                if dt > 0:
                    vy = (center[1] - self._prev_center[1]) / height / dt
                    vx = (center[0] - self._prev_center[0]) / width / dt
                    self._vy_hist.append(vy)
                    self._vx_hist.append(vx)
                    vy = sum(self._vy_hist) / len(self._vy_hist)
                    vx = sum(self._vx_hist) / len(self._vx_hist)
            if self._prev_tilt is not None and self._prev_time is not None:
                dt = now - self._prev_time
                if dt > 0:
                    tilt_vel = (tilt - self._prev_tilt) / dt

            if self._v2_scorer is not None:
                if self._scorer_version >= 4:
                    tilt3d = extra["tilt3d"]
                    if tilt3d is None:      # world landmarks 미제공 프레임 - 2D 로 대체
                        tilt3d = tilt
                    risk_score = self._v2_scorer.update(
                        vy, vx, tilt, tilt_vel,
                        tilt3d=tilt3d, aspect=extra["aspect"],
                        shoulder_y=extra["shoulder_y"])
                else:
                    risk_score = self._v2_scorer.update(vy, vx, tilt, tilt_vel)
                is_risky = risk_score >= self.prob_threshold
            elif self.model_bundle is not None:
                risk_score = self.model_bundle["model"].predict_proba(
                    [[vy, vx, tilt, tilt_vel]])[0][1]
                is_risky = risk_score >= self.prob_threshold
            else:
                risk_score = vy
                is_risky = vy > VELOCITY_THRESHOLD

            # 방향은 몸통 중심의 화면 이동(vx, vy)에서, lean 은 화면 기울기(tilt)에서
            # 구한다. 둘 다 이미지 좌표만 쓰므로 신뢰 못 할 z 에 의존하지 않는다.
            direction_deg = tiles.direction_from_motion(vx, vy, self.camera_yaw_deg)
            lean_ratio = tiles.lean_from_tilt(tilt)

            self._prev_center = center
            self._prev_tilt = tilt
            self._prev_time = now

            yield PoseFrame(image=image, landmarks=landmarks, timestamp=now,
                            risk_score=float(risk_score), is_risky=bool(is_risky),
                            direction_deg=direction_deg, lean_ratio=lean_ratio,
                            face_name=face_name)

    def release(self):
        # 일시 해제 상태(frames() 가 카메라를 놓아둔 상태)면 이미 None 이다.
        if self._video is not None:
            self._video.release()
            self._video = None
