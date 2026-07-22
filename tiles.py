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


# 규칙 3 이 발동하려면 방향이 대각 중심에서 이 각도 이내여야 한다.
# 구간 경계 부근(예: 30도)에서 확신이 높다는 이유만으로 모서리 한 장에
# 투신하는 것을 막는다.
DIAGONAL_TOLERANCE_DEG = 10.0

# 대각 섹터(1, 3, 5, 7)의 반대편 섹터
_OPPOSITE_SECTOR = {1: 5, 3: 7, 5: 1, 7: 3}


def _sector_of(direction_deg):
    """방향을 8구간(0=먼쪽, 1=먼쪽·우, 2=우, ...)으로 양자화한다.

    round() 대신 floor(x + 0.5) 를 쓴다. 파이썬의 round() 는 은행가 반올림이라
    22.5 와 67.5 같은 정확한 경계값에서 올림/내림이 엇갈린다.
    """
    return int(math.floor((direction_deg % 360.0) / 45.0 + 0.5)) % 8


def _corner_tile(sector, rows, cols):
    """대각 섹터에 해당하는 모서리 타일 번호 (행 우선 번호 규약)."""
    if sector == 1:                      # 먼쪽·우
        return cols - 1
    if sector == 3:                      # 가까운쪽·우
        return rows * cols - 1
    if sector == 5:                      # 가까운쪽·좌
        return (rows - 1) * cols
    return 0                             # 7: 먼쪽·좌


def _angle_offset(direction_deg, center_deg):
    """두 각도의 최단 거리(0~180)."""
    return abs((direction_deg - center_deg + 180.0) % 360.0 - 180.0)


def select_tiles(direction_deg, R, lean_ratio, rows, cols,
                 tau_R, tau_R_strict, tau_lean):
    """낙상 방향과 확신도에서 작동시킬 타일 집합을 결정한다.

    순수 함수다. 하드웨어도 카메라도 필요 없다.
    반환 집합의 크기는 항상 1, 2, 3, 4 중 하나이며 빈 집합이 아니다.
    """
    all_tiles = set(range(rows * cols))

    # 게이트: 판정이 불확실하면 전부 켠다. 규칙보다 우선한다.
    #   R < tau_R        방향이 프레임마다 튐 - 판정 불가
    #   lean < tau_lean  수직으로 주저앉음 - 방향이 애초에 존재하지 않음
    if R < tau_R or lean_ratio < tau_lean:
        return all_tiles

    sector = _sector_of(direction_deg)

    # 규칙 1: 정방향 -> 그 방향의 행 또는 열 전체
    if sector % 2 == 0:
        if sector == 0:                                        # 먼 쪽
            return {c for c in range(cols)}
        if sector == 2:                                        # 우
            return {r * cols + (cols - 1) for r in range(rows)}
        if sector == 4:                                        # 가까운 쪽
            return {(rows - 1) * cols + c for c in range(cols)}
        return {r * cols for r in range(rows)}                  # 6: 좌

    # 규칙 3: 대각이면서 방향이 아주 깨끗하면 모서리 한 장만
    if (R >= tau_R_strict
            and _angle_offset(direction_deg, sector * 45.0) <= DIAGONAL_TOLERANCE_DEG):
        return {_corner_tile(sector, rows, cols)}

    # 규칙 2: 대각 -> 전체에서 반대편 모서리 한 장 제외
    return all_tiles - {_corner_tile(_OPPOSITE_SECTOR[sector], rows, cols)}
