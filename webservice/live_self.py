"""관람객 '내 카메라 체험' — 브라우저가 보낸 포즈 랜드마크로 낙상 판정.

구조:
  브라우저(MediaPipe Tasks JS)가 카메라에서 랜드마크만 추출해 WebSocket 으로
  보낸다. 영상 픽셀은 기기 밖으로 나가지 않는다 — '자세만 보고 영상은 보내지
  않는다'는 제품 약속이 온라인 체험에서는 문자 그대로 성립한다.

  서버는 main.py 파이프라인과 같은 특징 정의(pose_source._detect_pose /
  extract_features_v4.py)와 같은 스코어러(temporal_risk.TemporalRiskScorer)로
  프레임별 위험 확률을 계산하고, persistence·쿨다운·타일 선택까지 main.py 의
  판정 로직을 그대로 재현해 이벤트를 돌려준다.

의존성 주의: 배포 서버에는 mediapipe 가 없다(이미지 크기 때문에 의도적으로 뺌).
  포즈 추출은 전부 브라우저 몫이므로 서버는 joblib + scikit-learn 만 있으면 된다.
  그것마저 없는 환경(CI 최소 테스트)에서는 load_bundle() 이 None 을 돌려주고
  라우트가 '체험 불가'로 응답한다 — 서버가 죽지 않는다.
"""

import math
import os
from collections import deque, namedtuple

# 저장소 루트 모듈(순수 표준 라이브러리 — mediapipe/cv2 의존 없음)
import tiles
from numpy_compat import bitgen_compat

L_SHOULDER, R_SHOULDER = 11, 12
L_HIP, R_HIP = 23, 24
L_ANKLE, R_ANKLE = 27, 28      # v6: 발목이 바닥 기준선

SMOOTHING_WINDOW = 3     # pose_source.SMOOTHING_WINDOW 와 동일
RISK_COOLDOWN = 3.0      # main.py 와 동일
RESET_DELAY = 2.0        # main.py 와 동일
MAX_FPS = 40.0           # 이보다 빨리 오는 프레임은 버린다 (클라이언트 폭주 방지)

_BUNDLE = None
_BUNDLE_TRIED = False

# 특징을 이름으로 받는다. 위치 기반 튜플이었을 때 v6 값 4개를 뒤에 붙이자마자
# 끝에서부터 언패킹하던 코드가 조용히 어긋났다 — 이름이면 그런 일이 없다.
Features = namedtuple("Features",
                      "vy vx tilt tilt_vel tilt3d aspect shoulder_y "
                      "torso_n body_n hip_y ankle_y")


def load_bundle():
    """낙상 위험 모델 번들. sklearn/joblib 또는 모델 파일이 없으면 None."""
    global _BUNDLE, _BUNDLE_TRIED
    if _BUNDLE_TRIED:
        return _BUNDLE
    _BUNDLE_TRIED = True
    try:
        import joblib
        import pandas  # noqa: F401 - temporal_risk 가 쓴다. 없으면 여기서 미리 거른다
        import sklearn  # noqa: F401
    except ImportError:
        print("[self-cam] joblib/pandas/scikit-learn 미설치 — 체험 기능 비활성")
        return None
    for path in ("fall_risk_model_v6.joblib", "fall_risk_model_v5.joblib",
                 "fall_risk_model_v4.joblib", "fall_risk_model_v3.joblib",
                 "fall_risk_model_v2.joblib"):
        if not os.path.isfile(path):
            continue
        try:
            # 모델은 numpy 2.x 로 학습됐는데 배포는 numpy 1.26 에 고정돼 있다
            # (mediapipe 제약). shim 없이는 네 버전 전부 로드에 실패해서
            # 체험 기능이 항상 꺼진다.
            with bitgen_compat():
                bundle = joblib.load(path)
        except Exception as exc:            # noqa: BLE001 - 다음 버전으로 폴백
            print(f"[self-cam] {path} 로드 실패, 건너뜀: {exc}")
            continue
        if bundle.get("version", 1) < 2:
            continue                        # TemporalRiskScorer 는 v2+ 전용
        print(f"[self-cam] 모델 로드: {path} (v{bundle.get('version')})")
        _BUNDLE = bundle
        return _BUNDLE
    print("[self-cam] 모델 파일 없음 — 체험 기능 비활성")
    return None


def _load_thresholds():
    """profiles.json 의 human 프로파일. 없으면 v4 보고서의 기본 동작점."""
    try:
        import config
        p = config.load_profile("human")
        return {"prob_threshold": p.prob_threshold, "persistence": p.persistence,
                "tau_R": p.tau_R, "tau_R_strict": p.tau_R_strict,
                "tau_lean": p.tau_lean, "window": p.window}
    except Exception:                       # noqa: BLE001
        return {"prob_threshold": 0.1, "persistence": 3,
                "tau_R": 0.5, "tau_R_strict": 0.8, "tau_lean": 0.35, "window": 5}


class SessionLimiter:
    """동시 체험 세션 수 제한. 세션당 프레임마다 모델 추론(~3ms)이 돌므로
    무제한으로 받으면 몇 명만 붙어도 서버가 밀린다."""

    def __init__(self, limit=None):
        self.limit = limit or int(os.environ.get("DAON_SELF_MAX", "3"))
        self.active = 0

    def acquire(self):
        if self.active >= self.limit:
            return False
        self.active += 1
        return True

    def release(self):
        self.active = max(0, self.active - 1)


class SelfSession:
    """WebSocket 연결 1개 = 체험 세션 1개.

    process(msg) 가 프레임 메시지 하나를 받아 브라우저로 보낼 이벤트 목록을
    돌려준다. 특징 계산은 pose_source 의 정의를 랜드마크(정규화 좌표) 기준으로
    옮긴 것 — 픽셀 좌표를 width/height 로 되돌려 나누는 대신 정규화 좌표를
    그대로 쓰되, 화면비가 필요한 tilt/aspect 만 w·h 를 곱해 계산한다.
    """

    def __init__(self, bundle, thresholds=None, scorer=None):
        th = thresholds or _load_thresholds()
        if scorer is None:
            # 지연 임포트: temporal_risk 는 pandas 를 요구한다. 최소 환경(CI)은
            # 이 클래스를 가짜 스코어러로만 쓰므로 모듈 임포트를 강제하지 않는다.
            from temporal_risk import TemporalRiskScorer
            scorer = TemporalRiskScorer(bundle)
        self.scorer = scorer
        self.prob_threshold = th["prob_threshold"]
        self.persistence = th["persistence"]
        self.tau_R = th["tau_R"]
        self.tau_R_strict = th["tau_R_strict"]
        self.tau_lean = th["tau_lean"]
        self.rows = 2
        self.cols = 2
        self._version = bundle.get("version", 2)
        self._vy_hist = deque(maxlen=SMOOTHING_WINDOW)
        self._vx_hist = deque(maxlen=SMOOTHING_WINDOW)
        self._window = deque(maxlen=th["window"])
        self._prev_center = None
        self._prev_tilt = None
        self._prev_time = None
        self._last_msg_time = None
        self._streak = 0
        self._last_fire = -RISK_COOLDOWN
        self._reset_pending = False

    def _reset_history(self):
        self._vy_hist.clear()
        self._vx_hist.clear()
        self._window.clear()
        self._prev_center = None
        self._prev_tilt = None
        self._prev_time = None
        self._streak = 0
        self.scorer.reset()

    # --- 특징 계산 (extract_features_v4.py 정의와 일치) ---

    @staticmethod
    def _mid(lm, a, b):
        return ((lm[a][0] + lm[b][0]) / 2.0, (lm[a][1] + lm[b][1]) / 2.0)

    def _features(self, lm, wlm, w, h, now):
        shoulder = self._mid(lm, L_SHOULDER, R_SHOULDER)
        hip = self._mid(lm, L_HIP, R_HIP)
        dx = (hip[0] - shoulder[0]) * w
        dy = (hip[1] - shoulder[1]) * h
        tilt = math.degrees(math.atan2(abs(dx), abs(dy) + 1e-6))

        center = ((shoulder[0] + hip[0]) / 2.0, (shoulder[1] + hip[1]) / 2.0)
        vy = vx = tilt_vel = 0.0
        if self._prev_center is not None and self._prev_time is not None:
            dt = now - self._prev_time
            if dt > 0:
                # pose_source: (픽셀 이동/height)/dt == 정규화 이동/dt
                vy = (center[1] - self._prev_center[1]) / dt
                vx = (center[0] - self._prev_center[0]) / dt
                self._vy_hist.append(vy)
                self._vx_hist.append(vx)
                vy = sum(self._vy_hist) / len(self._vy_hist)
                vx = sum(self._vx_hist) / len(self._vx_hist)
        if self._prev_tilt is not None and self._prev_time is not None:
            dt = now - self._prev_time
            if dt > 0:
                tilt_vel = (tilt - self._prev_tilt) / dt

        xs = [p[0] for p in lm]
        ys = [p[1] for p in lm]
        aspect = ((max(xs) - min(xs)) * w) / (((max(ys) - min(ys)) * h) + 1e-6)
        shoulder_y = (lm[L_SHOULDER][1] + lm[R_SHOULDER][1]) / 2.0

        # v6 정규화용 원시 길이. extract_v6.py / pose_source.py 와 같은 식이다
        # (랜드마크가 이미 정규화 좌표라 화면 크기를 곱하지 않는다).
        torso_n = math.hypot(hip[0] - shoulder[0], hip[1] - shoulder[1])
        body_n = max(ys) - min(ys)
        hip_y = hip[1]
        ankle_y = (lm[L_ANKLE][1] + lm[R_ANKLE][1]) / 2.0

        tilt3d = None
        if wlm:
            wdx = (wlm[L_HIP][0] + wlm[R_HIP][0]) / 2 - (wlm[L_SHOULDER][0] + wlm[R_SHOULDER][0]) / 2
            wdy = (wlm[L_HIP][1] + wlm[R_HIP][1]) / 2 - (wlm[L_SHOULDER][1] + wlm[R_SHOULDER][1]) / 2
            wdz = (wlm[L_HIP][2] + wlm[R_HIP][2]) / 2 - (wlm[L_SHOULDER][2] + wlm[R_SHOULDER][2]) / 2
            tilt3d = math.degrees(math.atan2(math.hypot(wdx, wdz), abs(wdy) + 1e-9))
        if tilt3d is None:
            tilt3d = tilt                   # pose_source 와 같은 폴백

        self._prev_center = center
        self._prev_tilt = tilt
        self._prev_time = now
        return Features(vy, vx, tilt, tilt_vel, tilt3d, aspect, shoulder_y,
                        torso_n, body_n, hip_y, ankle_y)

    # --- 프레임 처리 ---

    def process(self, msg):
        """프레임 메시지 → 브라우저로 보낼 이벤트 목록.

        msg: {"t": 초 단위 타임스탬프, "w": 폭, "h": 높이,
              "lm": [[x,y,z]×33] | null, "wlm": [[x,y,z]×33] | null}
        """
        now = float(msg.get("t", 0.0))

        # 클라이언트가 너무 빨리 보내면 버린다 — 판정 품질보다 서버 보호가 먼저.
        if self._last_msg_time is not None and now - self._last_msg_time < 1.0 / MAX_FPS:
            return []
        self._last_msg_time = now

        events = []
        if self._reset_pending and now - self._last_fire > RESET_DELAY:
            self._reset_pending = False
            events.append({"type": "reset"})

        lm = msg.get("lm")
        if not lm:
            self._reset_history()
            events.append({"type": "self", "risk": 0.0,
                           "prog": [0, self.persistence]})
            return events

        w = float(msg.get("w") or 640)
        h = float(msg.get("h") or 480)
        ft = self._features(lm, msg.get("wlm"), w, h, now)

        if self._version >= 6:
            risk = self.scorer.update(ft.vy, ft.vx, ft.tilt, ft.tilt_vel,
                                      tilt3d=ft.tilt3d, aspect=ft.aspect,
                                      shoulder_y=ft.shoulder_y,
                                      torso_n=ft.torso_n, body_n=ft.body_n,
                                      hip_y=ft.hip_y, ankle_y=ft.ankle_y)
        elif self._version >= 4:
            risk = self.scorer.update(ft.vy, ft.vx, ft.tilt, ft.tilt_vel,
                                      tilt3d=ft.tilt3d, aspect=ft.aspect,
                                      shoulder_y=ft.shoulder_y)
        else:
            risk = self.scorer.update(ft.vy, ft.vx, ft.tilt, ft.tilt_vel)

        if risk >= self.prob_threshold:
            direction = tiles.direction_from_motion(ft.vx, ft.vy)
            lean = tiles.lean_from_tilt(ft.tilt)
            self._window.append((direction, lean))
            self._streak += 1
        else:
            self._window.clear()
            self._streak = 0

        events.append({"type": "self", "risk": round(float(risk), 3),
                       "prog": [self._streak, self.persistence]})

        if (self._streak >= self.persistence
                and now - self._last_fire > RISK_COOLDOWN):
            direction, R, lean = tiles.resolve_direction(self._window)
            fired = tiles.select_tiles(direction, R, lean, self.rows, self.cols,
                                       self.tau_R, self.tau_R_strict, self.tau_lean)
            if len(fired) > 1:              # main.py 와 동일: 한 번에 1장
                fired = {min(fired)}
            events.append({"type": "fall", "tiles": sorted(fired),
                           "rows": self.rows, "cols": self.cols,
                           "direction": round(float(direction), 1)})
            self._last_fire = now
            self._streak = 0
            self._window.clear()
            self._reset_pending = True

        return events
