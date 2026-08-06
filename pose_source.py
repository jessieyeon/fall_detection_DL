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
import os
from collections import deque
from dataclasses import dataclass
from time import time

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


def load_risk_model(path="fall_risk_model.joblib", v2_path="fall_risk_model_v2.joblib",
                    v3_path="fall_risk_model_v3.joblib", v4_path="fall_risk_model_v4.joblib",
                    v5_path="fall_risk_model_v5.joblib"):
    # 최신 버전 우선: v5(도메인불변+의사라벨) > v4(3D) > v3 > v2 > v1 > 속도 임계값
    for p, ver in ((v5_path, "v5"), (v4_path, "v4"), (v3_path, "v3"), (v2_path, "v2")):
        if os.path.isfile(p):
            bundle = joblib.load(p)
            print(f"낙상 위험 모델 {ver} 로드됨 (threshold={bundle['prob_threshold']}, "
                  f"persistence={bundle['persistence']} 값은 참고용이며, "
                  "실제로는 프로파일(profiles.json) 값으로 덮어써서 사용합니다)")
            return bundle
    if not os.path.isfile(path):
        print(f"경고: {path} 가 없습니다 - 단일 수직속도 임계값"
              f"({VELOCITY_THRESHOLD})으로 대체합니다.")
        return None
    bundle = joblib.load(path)
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
                 tile_grid=None, face_every=0, face_recognizer=None):
        self.video_source = video_source
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
        while self._video.isOpened():
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
        self._video.release()
