"""낙상 방향 추정과 타일 선택.

의존성은 표준 라이브러리(math)뿐이다. mediapipe, opencv, pyserial 어느 것에도
의존하지 않으므로 카메라나 아두이노 없이 전부 단위 테스트로 검증된다.

각도 규약: 0도 = 격자 위쪽(카메라에서 먼 쪽), 시계방향 증가.
           90도 = 우, 180도 = 앞(카메라 쪽), 270도 = 좌.
"""

import math

# MediaPipe Pose 랜드마크 인덱스 (main.py 의 기존 정의와 동일하게 유지)
L_SHOULDER, R_SHOULDER = 11, 12
L_HIP, R_HIP = 23, 24


def _midpoint(landmarks, left_index, right_index):
    left = landmarks[left_index]
    right = landmarks[right_index]
    return (
        (left[0] + right[0]) / 2.0,
        (left[1] + right[1]) / 2.0,
        (left[2] + right[2]) / 2.0,
    )


def lean_from_landmarks(landmarks, camera_yaw_deg=0.0):
    """어깨 중점에서 엉덩이 중점으로 향하는 몸통 벡터에서 낙상 방향을 구한다.

    발목(27, 28)은 쓰지 않는다. 집 모형 안에서 가려지기 쉽고 인형에서 인식되지
    않을 위험이 크기 때문이다. 어깨와 엉덩이는 낙상 모델의 입력이라 어차피 잘
    인식되어야만 하는 값이다.

    반환값 (direction_deg, lean_ratio):
      direction_deg  [0, 360). 몸통이 기운 방향.
      lean_ratio     [0, 1]. 기울기의 사인값. 0 = 직립, 1 = 완전히 누움.
                     화면상 크기에 무관하므로 인형과 사람에 같은 임계값을 쓸 수 있다.
    """
    sx, sy, sz = _midpoint(landmarks, L_SHOULDER, R_SHOULDER)
    hx, hy, hz = _midpoint(landmarks, L_HIP, R_HIP)

    dx = sx - hx           # + = 오른쪽
    dy = sy - hy           # + = 아래 (이미지 좌표)
    dz = sz - hz           # + = 카메라에서 멀어짐

    torso_length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if torso_length < 1e-6:
        return 0.0, 0.0

    lean_ratio = math.hypot(dx, dz) / torso_length
    direction_deg = (math.degrees(math.atan2(dx, dz)) - camera_yaw_deg) % 360.0
    return direction_deg, lean_ratio


def resolve_direction(window):
    """최근 N프레임의 표본에서 대표 방향과 방향 일치도를 구한다.

    window: (direction_deg, lean_ratio) 튜플의 시퀀스.

    반환값 (mean_direction_deg, R, mean_lean_ratio):
      R 은 원형통계의 평균 결과 길이다. 표본들이 같은 방향을 가리키면 1에 가깝고
      흩어지면 0에 가깝다. 이 값을 방향 확신도로 사용한다.
    """
    if not window:
        return 0.0, 0.0, 0.0

    sin_sum = sum(math.sin(math.radians(d)) for d, _ in window)
    cos_sum = sum(math.cos(math.radians(d)) for d, _ in window)
    n = len(window)

    mean_direction_deg = math.degrees(math.atan2(sin_sum, cos_sum))
    if mean_direction_deg < 0:
        mean_direction_deg += 360.0
    # 부동소수점 반올림으로 인한 360 처리
    if mean_direction_deg >= 360.0:
        mean_direction_deg = 0.0
    R = math.hypot(sin_sum, cos_sum) / n
    mean_lean_ratio = sum(lean for _, lean in window) / n
    return mean_direction_deg, R, mean_lean_ratio
