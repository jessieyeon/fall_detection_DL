# 멀티 타일 동시 작동 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 낙상 방향에 따라 충격 완화 타일 1~4장을 동시에 작동시키고, 응답 확인이 가능한 시리얼 프로토콜로 아두이노에 전달한다.

**Architecture:** 몸통 기울기 벡터에서 낙상 방향과 확신도를 계산하고, 규칙 기반 순수 함수로 타일 집합을 결정한 뒤, 줄 단위 텍스트 프로토콜로 펌웨어에 전송한다. 핵심 로직(`tiles.py`, `tile_protocol.py`)은 mediapipe·opencv·카메라에 의존하지 않아 하드웨어 없이 전부 단위 테스트된다. 기존 `main.py`의 337줄 단일 스크립트에서 카메라 어댑터와 캘리브레이션을 분리해 조립부만 남긴다.

**Tech Stack:** Python 3, MediaPipe 0.10.14, OpenCV, scikit-learn(joblib), pyserial, pytest / Arduino C++ (Adafruit PCA9685)

**설계 문서:** `docs/superpowers/specs/2026-07-22-multi-tile-activation-design.md`

## Global Constraints

- **타일 번호는 어디서나 0-indexed.** 파이썬, `calibration.json`, 로그, 시리얼 프로토콜 전부 `0`~`rows*cols-1`. 타일↔PCA9685 채널 매핑은 `.ino` 안에만 존재한다.
- **격자 번호는 행 우선(row-major).** 2×2에서 `0 1 / 2 3`, row 0 = 카메라에서 먼 쪽.
- **방향 각도 규약:** `0° = 격자 위쪽(카메라에서 먼 쪽)`, 시계방향 증가. 90°=우, 180°=앞, 270°=좌.
- **기존 `tiltAngleDeg()`의 정의를 바꾸지 않는다.** 학습된 `fall_risk_model.joblib`의 입력 특징이므로 변경 시 학습/서빙 불일치가 발생한다. 모델 입력 특징은 `[vy, vx, tilt, tilt_vel]` 순서 그대로 유지한다.
- **시리얼 보율 115200.** 파이썬과 `.ino` 양쪽.
- **응답 타임아웃 200ms.** ACK 실패는 경고만 남기고 진행한다. `fire()`/`reset()`/`ping()`은 예외를 던지지 않고 `bool`을 반환한다.
- **모든 판정 파라미터는 `profiles.json`에 둔다.** 코드 상수로 두지 않는다.
- **주석과 로그 메시지는 한국어**, 코드 식별자는 영어. 기존 코드베이스 관행을 따른다.

## File Structure

| 파일 | 책임 | 상태 |
|---|---|---|
| `tiles.py` | 방향 추정 + 타일 선택. 의존성 `math`뿐 | 신규 |
| `tile_protocol.py` | 시리얼 프로토콜. 의존성 `pyserial`뿐 | 신규 |
| `config.py` | `profiles.json` 로드와 검증 | 신규 |
| `calibration.py` | 호모그래피 로드 / 픽셀→타일 / 격자 렌더링 | 신규 (`main.py`에서 이동) |
| `pose_source.py` | 카메라 입력 어댑터. 프레임 → 포즈 → 특징 → 위험도 | 신규 (`main.py`에서 이동) |
| `main.py` | 조립부. CLI, 발사 상태 기계, 로깅, 화면 출력 | 대폭 축소 |
| `profiles.json` | 프로파일 파라미터 | 신규 |
| `hardware/four_servo_control/four_servo_control.ino` | 펌웨어 | 수정 |
| `tests/test_tiles.py` | | 신규 |
| `tests/test_tile_protocol.py` | | 신규 |
| `tests/test_config.py` | | 신규 |
| `requirements.txt` | pytest 추가 | 수정 |
| `README.md` | 프로토콜·CLI·프로파일 문서화 | 수정 |

**Task 1~4, 5a, 6은 하드웨어·카메라·인형 없이 완결된다.** Task 7~9는 카메라가,
Task 5b는 아두이노가 필요하다.

**Task 5b는 아두이노 확보 후로 미룬다.** 소프트웨어 상 아무것도 막지 않는다 —
Task 6~9는 `.ino` 에 의존하지 않고, 파이썬 쪽은 `--no-serial` 과 시뮬레이션 모드로
끝까지 돌아간다. 다만 **가정 A2(서보 4개 동시 기동 전원)가 Task 5b 전까지 미검증으로
남는다**는 점은 계속 열린 위험이다.

---

## Task 1: 테스트 기반과 방향 벡터 계산

**Files:**
- Create: `tiles.py`
- Create: `tests/test_tiles.py`
- Modify: `requirements.txt`

**Interfaces:**
- Consumes: 없음 (첫 태스크)
- Produces:
  - `tiles.L_SHOULDER = 11`, `tiles.R_SHOULDER = 12`, `tiles.L_HIP = 23`, `tiles.R_HIP = 24`
  - `tiles.lean_from_landmarks(landmarks, camera_yaw_deg=0.0) -> tuple[float, float]`
    — `(direction_deg, lean_ratio)`. `landmarks`는 `(x, y, z)` 튜플의 시퀀스로, 인덱스는 MediaPipe Pose 규약을 따른다. `direction_deg`는 `[0, 360)`, `lean_ratio`는 `[0, 1]`.

- [ ] **Step 1: pytest를 requirements.txt에 추가**

`requirements.txt` 맨 끝에 한 줄 추가한다:

```
pytest==8.2.0
```

설치:

```bash
pip install pytest==8.2.0
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_tiles.py` 를 새로 만든다:

```python
import math

import pytest

import tiles


def make_landmarks(shoulder, hip):
    """MediaPipe Pose 랜드마크 33개짜리 리스트를 만들되 어깨(11,12)와
    엉덩이(23,24)만 채운다. 나머지는 이 모듈이 읽지 않는다."""
    lm = [(0.0, 0.0, 0.0)] * 33
    lm[tiles.L_SHOULDER] = shoulder
    lm[tiles.R_SHOULDER] = shoulder
    lm[tiles.L_HIP] = hip
    lm[tiles.R_HIP] = hip
    return lm


def test_upright_torso_has_zero_lean_ratio():
    # 어깨가 엉덩이 바로 위(이미지 y는 아래가 +)
    lm = make_landmarks(shoulder=(100.0, 100.0, 0.0), hip=(100.0, 200.0, 0.0))
    _, lean_ratio = tiles.lean_from_landmarks(lm)
    assert lean_ratio == pytest.approx(0.0, abs=1e-6)


def test_leaning_right_is_90_degrees():
    # 어깨가 엉덩이보다 오른쪽(+x)
    lm = make_landmarks(shoulder=(200.0, 100.0, 0.0), hip=(100.0, 200.0, 0.0))
    direction, lean_ratio = tiles.lean_from_landmarks(lm)
    assert direction == pytest.approx(90.0)
    assert lean_ratio == pytest.approx(math.sqrt(0.5))


def test_leaning_left_is_270_degrees():
    lm = make_landmarks(shoulder=(0.0, 100.0, 0.0), hip=(100.0, 200.0, 0.0))
    direction, _ = tiles.lean_from_landmarks(lm)
    assert direction == pytest.approx(270.0)


def test_leaning_away_from_camera_is_0_degrees():
    # z 가 커질수록 카메라에서 멀어진다
    lm = make_landmarks(shoulder=(100.0, 100.0, 100.0), hip=(100.0, 200.0, 0.0))
    direction, _ = tiles.lean_from_landmarks(lm)
    assert direction == pytest.approx(0.0)


def test_leaning_toward_camera_is_180_degrees():
    lm = make_landmarks(shoulder=(100.0, 100.0, -100.0), hip=(100.0, 200.0, 0.0))
    direction, _ = tiles.lean_from_landmarks(lm)
    assert direction == pytest.approx(180.0)


def test_camera_yaw_rotates_the_direction():
    # 카메라가 격자 대비 90도 돌아가 있으면 "이미지상 우측"이 격자상 0도가 된다
    lm = make_landmarks(shoulder=(200.0, 100.0, 0.0), hip=(100.0, 200.0, 0.0))
    direction, _ = tiles.lean_from_landmarks(lm, camera_yaw_deg=90.0)
    assert direction == pytest.approx(0.0)


def test_fully_horizontal_torso_has_lean_ratio_one():
    # 어깨와 엉덩이의 y가 같으면 완전히 누운 상태
    lm = make_landmarks(shoulder=(200.0, 100.0, 0.0), hip=(100.0, 100.0, 0.0))
    _, lean_ratio = tiles.lean_from_landmarks(lm)
    assert lean_ratio == pytest.approx(1.0)


def test_degenerate_zero_length_torso_does_not_divide_by_zero():
    lm = make_landmarks(shoulder=(100.0, 100.0, 0.0), hip=(100.0, 100.0, 0.0))
    direction, lean_ratio = tiles.lean_from_landmarks(lm)
    assert direction == 0.0
    assert lean_ratio == 0.0
```

- [ ] **Step 3: 테스트를 실행해 실패를 확인**

```bash
cd /Users/Yeon/Desktop/fall_detection_DL && python -m pytest tests/test_tiles.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'tiles'`

- [ ] **Step 4: 최소 구현 작성**

`tiles.py` 를 새로 만든다:

```python
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
```

- [ ] **Step 5: 테스트를 실행해 통과를 확인**

```bash
cd /Users/Yeon/Desktop/fall_detection_DL && python -m pytest tests/test_tiles.py -v
```

Expected: PASS — 8 passed

- [ ] **Step 6: 커밋**

```bash
git add tiles.py tests/test_tiles.py requirements.txt
git commit -m "feat: add signed fall direction from torso lean vector"
```

---

## Task 2: 발사 시점의 원형 평균 판정

프레임마다 방향을 재판정하면 구간 경계에서 값이 진동한다. 최근 N프레임의 표본을
모아두었다가 발사가 확정되는 순간 한 번만 계산한다. 각도이므로 산술평균은
틀린다 — 350도와 10도의 산술평균은 180도가 되어 정반대를 가리킨다.

**Files:**
- Modify: `tiles.py`
- Modify: `tests/test_tiles.py`

**Interfaces:**
- Consumes: Task 1의 `tiles.py`
- Produces:
  - `tiles.resolve_direction(window) -> tuple[float, float, float]`
    — `window`는 `(direction_deg, lean_ratio)` 튜플의 시퀀스.
      반환은 `(mean_direction_deg, R, mean_lean_ratio)`.
      `R`은 원형통계의 평균 결과 길이로 `[0, 1]`, 방향 일치도를 뜻한다.
      빈 시퀀스면 `(0.0, 0.0, 0.0)`.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_tiles.py` 맨 끝에 추가한다:

```python
def test_circular_mean_wraps_around_zero():
    # 산술평균이면 180도가 나온다. 이 함수가 존재하는 이유가 정확히 이것이다.
    mean_direction, _, _ = tiles.resolve_direction([(350.0, 0.5), (10.0, 0.5)])
    assert mean_direction == pytest.approx(0.0, abs=1e-6)


def test_identical_directions_give_R_of_one():
    window = [(90.0, 0.4)] * 5
    mean_direction, R, mean_lean = tiles.resolve_direction(window)
    assert mean_direction == pytest.approx(90.0)
    assert R == pytest.approx(1.0)
    assert mean_lean == pytest.approx(0.4)


def test_opposite_directions_give_R_of_zero():
    _, R, _ = tiles.resolve_direction([(0.0, 0.5), (180.0, 0.5)])
    assert R == pytest.approx(0.0, abs=1e-9)


def test_scattered_directions_lower_R():
    tight = [(90.0, 0.5), (92.0, 0.5), (88.0, 0.5)]
    loose = [(90.0, 0.5), (150.0, 0.5), (30.0, 0.5)]
    _, tight_R, _ = tiles.resolve_direction(tight)
    _, loose_R, _ = tiles.resolve_direction(loose)
    assert tight_R > loose_R


def test_mean_lean_ratio_is_the_arithmetic_mean():
    _, _, mean_lean = tiles.resolve_direction([(90.0, 0.2), (90.0, 0.6)])
    assert mean_lean == pytest.approx(0.4)


def test_empty_window_returns_zeros():
    assert tiles.resolve_direction([]) == (0.0, 0.0, 0.0)
```

- [ ] **Step 2: 테스트를 실행해 실패를 확인**

```bash
cd /Users/Yeon/Desktop/fall_detection_DL && python -m pytest tests/test_tiles.py -v -k resolve or circular
```

간단히 전체를 돌려도 된다:

```bash
cd /Users/Yeon/Desktop/fall_detection_DL && python -m pytest tests/test_tiles.py -v
```

Expected: FAIL — `AttributeError: module 'tiles' has no attribute 'resolve_direction'` (6건)

- [ ] **Step 3: 최소 구현 작성**

`tiles.py` 의 `lean_from_landmarks` 아래에 추가한다:

```python
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

    mean_direction_deg = math.degrees(math.atan2(sin_sum, cos_sum)) % 360.0
    R = math.hypot(sin_sum, cos_sum) / n
    mean_lean_ratio = sum(lean for _, lean in window) / n
    return mean_direction_deg, R, mean_lean_ratio
```

- [ ] **Step 4: 테스트를 실행해 통과를 확인**

```bash
cd /Users/Yeon/Desktop/fall_detection_DL && python -m pytest tests/test_tiles.py -v
```

Expected: PASS — 14 passed

- [ ] **Step 5: 커밋**

```bash
git add tiles.py tests/test_tiles.py
git commit -m "feat: add circular mean direction resolution with agreement metric"
```

---

## Task 3: 타일 선택 규칙과 게이트

설계 문서 §6.3, §6.4의 핵심이다. 규칙 세 개와 게이트 두 개로 타일 집합을 결정한다.

- 규칙 1 (정방향, 중심 ±22.5°): 그 방향의 행 또는 열 전체 → 2×2에서 2장
- 규칙 2 (대각, 중심 ±22.5°): 전체에서 반대편 모서리 한 장 제외 → 3장
- 규칙 3 (대각 정밀, 중심 ±10° 이내이고 `R >= tau_R_strict`): 그 모서리 한 장만 → 1장
- 게이트 (`R < tau_R` 또는 `lean_ratio < tau_lean`): 전체 4장. **규칙보다 우선한다.**

**Files:**
- Modify: `tiles.py`
- Modify: `tests/test_tiles.py`

**Interfaces:**
- Consumes: Task 1, 2의 `tiles.py`
- Produces:
  - `tiles.DIAGONAL_TOLERANCE_DEG = 10.0`
  - `tiles.select_tiles(direction_deg, R, lean_ratio, rows, cols, tau_R, tau_R_strict, tau_lean) -> set[int]`
    — 반환 집합의 크기는 항상 1, 2, 3, 4 중 하나이며 빈 집합이 아니다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_tiles.py` 맨 끝에 추가한다:

```python
# 2x2 격자에서 쓰는 기본 인자. 게이트는 통과하되 규칙 3(1장)은 발동하지 않는 값.
GRID = dict(rows=2, cols=2, tau_R=0.85, tau_R_strict=0.95, tau_lean=0.15)


def pick(direction_deg, R=0.90, lean_ratio=0.40, **overrides):
    kwargs = dict(GRID)
    kwargs.update(overrides)
    return tiles.select_tiles(direction_deg, R, lean_ratio, **kwargs)


# --- 규칙 1: 정방향은 행 또는 열 전체 (2장) ---

def test_cardinal_far_selects_top_row():
    assert pick(0.0) == {0, 1}


def test_cardinal_right_selects_right_column():
    assert pick(90.0) == {1, 3}


def test_cardinal_near_selects_bottom_row():
    assert pick(180.0) == {2, 3}


def test_cardinal_left_selects_left_column():
    assert pick(270.0) == {0, 2}


# --- 규칙 2: 대각은 반대편 모서리 제외 (3장) ---

def test_diagonal_far_right_excludes_near_left_corner():
    assert pick(45.0) == {0, 1, 3}


def test_diagonal_near_right_excludes_far_left_corner():
    assert pick(135.0) == {1, 2, 3}


def test_diagonal_near_left_excludes_far_right_corner():
    assert pick(225.0) == {0, 2, 3}


def test_diagonal_far_left_excludes_near_right_corner():
    assert pick(315.0) == {0, 1, 2}


# --- 규칙 3: 대각 정밀은 모서리 한 장 ---

def test_precise_diagonal_selects_single_corner():
    assert pick(45.0, R=0.97) == {1}
    assert pick(135.0, R=0.97) == {3}
    assert pick(225.0, R=0.97) == {2}
    assert pick(315.0, R=0.97) == {0}


def test_precise_diagonal_needs_both_angle_and_agreement():
    # 각도는 맞지만 R 이 tau_R_strict 미만이면 3장
    assert pick(45.0, R=0.94) == {0, 1, 3}
    # R 은 충분하지만 대각 중심에서 10도를 벗어나면 3장
    assert pick(34.9, R=0.99) == {0, 1, 3}


def test_precise_diagonal_tolerance_boundary():
    assert pick(35.0, R=0.99) == {1}      # 정확히 10도 — 포함
    assert pick(55.0, R=0.99) == {1}
    assert pick(34.9, R=0.99) == {0, 1, 3}
    assert pick(55.1, R=0.99) == {0, 1, 3}


def test_cardinal_never_narrows_to_one_tile():
    # 2x2 에서 "우측"만으로는 앞뒤 성분을 알 수 없으므로 열 전체를 덮어야 한다
    assert pick(90.0, R=1.0) == {1, 3}
    assert pick(0.0, R=1.0) == {0, 1}


# --- 게이트: 규칙보다 우선한다 ---

def test_low_agreement_fires_all_tiles():
    assert pick(90.0, R=0.50) == {0, 1, 2, 3}


def test_low_lean_ratio_fires_all_tiles():
    assert pick(90.0, lean_ratio=0.05) == {0, 1, 2, 3}


def test_gate_beats_precise_diagonal_rule():
    # 각도와 R 이 규칙 3을 만족해도 수직 붕괴면 4장이다
    assert pick(45.0, R=0.99, lean_ratio=0.05) == {0, 1, 2, 3}


# --- 구간 경계와 되감김 ---

def test_sector_boundary_at_22_5_degrees():
    assert pick(22.4) == {0, 1}          # 정방향(먼 쪽)
    assert pick(22.6) == {0, 1, 3}       # 대각


def test_wraps_around_360():
    assert pick(359.9) == {0, 1}
    assert pick(0.1) == {0, 1}
    assert pick(360.0) == {0, 1}


# --- 불변식 ---

@pytest.mark.parametrize("direction", [d * 3.0 for d in range(120)])
@pytest.mark.parametrize("R", [0.5, 0.86, 0.99])
@pytest.mark.parametrize("lean_ratio", [0.05, 0.4])
def test_result_size_is_always_one_to_four(direction, R, lean_ratio):
    result = pick(direction, R=R, lean_ratio=lean_ratio)
    assert 1 <= len(result) <= 4
    assert result <= {0, 1, 2, 3}
```

- [ ] **Step 2: 테스트를 실행해 실패를 확인**

```bash
cd /Users/Yeon/Desktop/fall_detection_DL && python -m pytest tests/test_tiles.py -v
```

Expected: FAIL — `AttributeError: module 'tiles' has no attribute 'select_tiles'`

- [ ] **Step 3: 최소 구현 작성**

`tiles.py` 맨 끝에 추가한다:

```python
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
```

- [ ] **Step 4: 테스트를 실행해 통과를 확인**

```bash
cd /Users/Yeon/Desktop/fall_detection_DL && python -m pytest tests/test_tiles.py -v
```

Expected: PASS — 751 passed
(Task 1의 8건 + Task 2의 6건 + 이번 17건 + 불변식 파라미터화 720건)

- [ ] **Step 5: 커밋**

```bash
git add tiles.py tests/test_tiles.py
git commit -m "feat: add rule-based tile selection with confidence gates"
```

---

## Task 4: 시리얼 프로토콜 클라이언트

**Files:**
- Create: `tile_protocol.py`
- Create: `tests/test_tile_protocol.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `tile_protocol.TileController(serial_factory=None)`
    — `serial_factory(port, baud, read_timeout)` 는 pyserial 호환 객체를 반환하는 콜러블. 테스트에서 가짜 객체를 주입하는 통로다.
  - `TileController.connect(port, baud=115200, ready_timeout=5.0) -> int`
    — `READY n` 을 받으면 `n`, 실패하면 `0`을 반환하고 시뮬레이션 모드가 된다.
  - `TileController.fire(tiles: set[int]) -> bool`
  - `TileController.reset() -> bool`
  - `TileController.ping() -> bool`
  - `TileController.close() -> None`
  - `TileController.simulated: bool`, `TileController.servo_count: int`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_tile_protocol.py` 를 새로 만든다:

```python
import time

import tile_protocol


class FakeSerial:
    """pyserial 의 최소 인터페이스만 흉내낸다."""

    def __init__(self, responses=None):
        self.written = []
        self.closed = False
        self._pending = list(responses or [])

    def reset_input_buffer(self):
        pass

    def write(self, data):
        self.written.append(data)

    def readline(self):
        if self._pending:
            return (self._pending.pop(0) + "\n").encode("ascii")
        return b""

    def close(self):
        self.closed = True


def make_controller(responses):
    fake = FakeSerial(responses)
    controller = tile_protocol.TileController(
        serial_factory=lambda port, baud, read_timeout: fake
    )
    return controller, fake


def test_connect_returns_servo_count_from_ready_line():
    controller, _ = make_controller(["READY 4"])
    assert controller.connect("/dev/fake") == 4
    assert controller.simulated is False
    assert controller.servo_count == 4


def test_connect_skips_comment_lines_before_ready():
    controller, _ = make_controller(["# 초기화 완료", "# FIRE 0,2", "READY 4"])
    assert controller.connect("/dev/fake") == 4


def test_connect_without_ready_falls_back_to_simulation():
    controller, fake = make_controller([])
    assert controller.connect("/dev/fake", ready_timeout=0.2) == 0
    assert controller.simulated is True
    assert fake.closed is True


def test_connect_with_no_port_is_simulation_mode():
    controller, _ = make_controller(["READY 4"])
    assert controller.connect(None) == 0
    assert controller.simulated is True


def test_connect_survives_serial_open_failure():
    def exploding_factory(port, baud, read_timeout):
        raise OSError("포트 없음")

    controller = tile_protocol.TileController(serial_factory=exploding_factory)
    assert controller.connect("/dev/nope") == 0
    assert controller.simulated is True


def test_fire_writes_sorted_csv_and_confirms_ack():
    controller, fake = make_controller(["READY 4", "OK FIRE 1,3"])
    controller.connect("/dev/fake")
    assert controller.fire({3, 1}) is True
    assert fake.written == [b"FIRE 1,3\n"]


def test_fire_single_tile():
    controller, fake = make_controller(["READY 4", "OK FIRE 2"])
    controller.connect("/dev/fake")
    assert controller.fire({2}) is True
    assert fake.written == [b"FIRE 2\n"]


def test_fire_all_four_tiles():
    controller, fake = make_controller(["READY 4", "OK FIRE 0,1,2,3"])
    controller.connect("/dev/fake")
    assert controller.fire({0, 1, 2, 3}) is True
    assert fake.written == [b"FIRE 0,1,2,3\n"]


def test_fire_with_empty_set_sends_nothing():
    controller, fake = make_controller(["READY 4"])
    controller.connect("/dev/fake")
    assert controller.fire(set()) is False
    assert fake.written == []


def test_err_response_returns_false_without_raising():
    controller, _ = make_controller(["READY 4", "ERR bad tile index"])
    controller.connect("/dev/fake")
    assert controller.fire({9}) is False


def test_missing_ack_returns_false_within_timeout():
    controller, _ = make_controller(["READY 4"])
    controller.connect("/dev/fake")
    started = time.monotonic()
    assert controller.fire({1}) is False
    # 설계 문서 §7.3: 응답 대기가 영상 루프를 오래 막으면 안 된다
    assert time.monotonic() - started < 0.5


def test_reset_and_ping():
    controller, fake = make_controller(["READY 4", "OK RESET", "OK PING"])
    controller.connect("/dev/fake")
    assert controller.reset() is True
    assert controller.ping() is True
    assert fake.written == [b"RESET\n", b"PING\n"]


def test_simulation_mode_does_not_write_or_raise():
    controller = tile_protocol.TileController()
    controller.connect(None)
    assert controller.fire({1, 3}) is False
    assert controller.reset() is False
```

- [ ] **Step 2: 테스트를 실행해 실패를 확인**

```bash
cd /Users/Yeon/Desktop/fall_detection_DL && python -m pytest tests/test_tile_protocol.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'tile_protocol'`

- [ ] **Step 3: 최소 구현 작성**

`tile_protocol.py` 를 새로 만든다:

```python
"""아두이노 타일 컨트롤러와의 줄 단위 텍스트 프로토콜.

의존성은 pyserial 뿐이다. mediapipe, opencv 에 의존하지 않는다.

프로토콜 (설계 문서 §7):
    파이썬 -> 아두이노     FIRE 1,3   RESET   PING
    아두이노 -> 파이썬     READY 4    OK FIRE 1,3   OK RESET   OK PING
                          ERR <사유>   # <사람이 읽을 주석, 무시됨>

타일 번호는 0-indexed 로 전선 위를 그대로 흐른다. 타일 번호와 PCA9685 채널의
매핑은 펌웨어 안에만 존재한다.
"""

import time

BAUD = 115200
SERIAL_READ_TIMEOUT = 0.05   # readline() 한 번이 블로킹되는 최대 시간(초)
RESPONSE_TIMEOUT = 0.2       # 명령 하나에 대한 응답을 기다리는 최대 시간(초)


def _default_serial_factory(port, baud, read_timeout):
    import serial  # 시뮬레이션 모드만 쓸 때 pyserial 을 강제하지 않으려고 지연 임포트

    return serial.Serial(port, baud, timeout=read_timeout)


class TileController:
    """타일 서보를 제어한다. 어떤 실패에도 예외를 밖으로 던지지 않는다.

    시연 도중 시리얼이 한 번 꼬였다고 프로그램이 죽는 것이 최악이므로,
    모든 명령은 성공 여부를 bool 로만 알린다.
    """

    def __init__(self, serial_factory=None):
        self._factory = serial_factory or _default_serial_factory
        self._serial = None
        self.simulated = True
        self.servo_count = 0

    # --- 연결 ---

    def connect(self, port, baud=BAUD, ready_timeout=5.0):
        """포트를 열고 READY 를 기다린다. 사용 가능한 서보 개수를 반환한다.

        대부분의 아두이노는 시리얼 포트가 열릴 때 리셋되고 setup() 에는
        delay(500) 이 있다. 핸드셰이크 없이 바로 명령을 보내면 부팅 중에
        삼켜진다.
        """
        if not port:
            print("[타일] 시리얼 포트가 지정되지 않음 - 시뮬레이션 모드로 실행합니다.")
            return self._fall_back_to_simulation()

        try:
            self._serial = self._factory(port, baud, SERIAL_READ_TIMEOUT)
        except Exception as exc:
            print(f"[타일] 경고: {port} 를 열 수 없습니다 ({exc}) - 시뮬레이션 모드.")
            return self._fall_back_to_simulation()

        try:
            self._serial.reset_input_buffer()
        except Exception:
            pass

        deadline = time.monotonic() + ready_timeout
        while time.monotonic() < deadline:
            line = self._read_line()
            if line is None:
                continue
            if line.startswith("READY"):
                parts = line.split()
                self.servo_count = int(parts[1]) if len(parts) > 1 else 0
                self.simulated = False
                print(f"[타일] 아두이노 연결됨 - 서보 {self.servo_count}개")
                return self.servo_count

        print(f"[타일] 경고: {port} 에서 READY 응답이 오지 않았습니다 - 시뮬레이션 모드.")
        self._close_serial()
        return self._fall_back_to_simulation()

    def _fall_back_to_simulation(self):
        self.simulated = True
        self.servo_count = 0
        return 0

    # --- 명령 ---

    def fire(self, tiles):
        """지정한 타일들을 동시에 작동시킨다. ACK 확인 여부를 반환한다."""
        if not tiles:
            return False
        payload = ",".join(str(t) for t in sorted(tiles))
        return self._command(f"FIRE {payload}", f"OK FIRE {payload}")

    def reset(self):
        """작동 중인 서보를 전부 원위치로 되돌린다."""
        return self._command("RESET", "OK RESET")

    def ping(self):
        return self._command("PING", "OK PING")

    def close(self):
        self._close_serial()

    # --- 내부 ---

    def _command(self, command, expected):
        if self.simulated:
            print(f"[모의] {command}")
            return False

        try:
            self._serial.write((command + "\n").encode("ascii"))
        except Exception as exc:
            print(f"[타일] 경고: '{command}' 전송 실패 ({exc})")
            return False

        deadline = time.monotonic() + RESPONSE_TIMEOUT
        while time.monotonic() < deadline:
            line = self._read_line()
            if line is None:
                continue
            if line == expected:
                return True
            print(f"[타일] 경고: 예상과 다른 응답 {line!r} (기대: {expected!r})")
            return False

        print(f"[타일] 경고: '{command}' 응답 시간 초과")
        return False

    def _read_line(self):
        """한 줄을 읽는다. 빈 줄과 '#' 주석은 None 으로 걸러낸다."""
        try:
            raw = self._serial.readline()
        except Exception:
            return None
        if not raw:
            return None
        line = raw.decode("ascii", errors="replace").strip()
        if not line or line.startswith("#"):
            return None
        return line

    def _close_serial(self):
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None
```

- [ ] **Step 4: 테스트를 실행해 통과를 확인**

```bash
cd /Users/Yeon/Desktop/fall_detection_DL && python -m pytest tests/test_tile_protocol.py -v
```

Expected: PASS — 13 passed

- [ ] **Step 5: 커밋**

```bash
git add tile_protocol.py tests/test_tile_protocol.py
git commit -m "feat: add line-based tile serial protocol with READY handshake"
```

---

## Task 5a: 펌웨어 — 텍스트 프로토콜 작성

**Files:**
- Modify: `hardware/four_servo_control/four_servo_control.ino` (전체 교체)

**Interfaces:**
- Consumes: Task 4가 정의한 프로토콜 문법
- Produces: `READY 4`, `OK FIRE <csv>`, `OK RESET`, `OK PING`, `ERR <사유>` 응답

**하드웨어 불필요.** 코드 작성과 컴파일 검증까지만 한다. 보드에 올려서 확인하는
것은 Task 5b이며, 아두이노를 확보한 뒤에 수행한다.

Task 4와 함께 작성하는 이유: `.ino`가 프로토콜 문법의 한쪽 끝이고 파이썬이 반대쪽
끝이다. `"OK FIRE 1,3"` 같은 문자열이 양쪽에서 정확히 일치해야 하므로 시차를 두고
작성하면 어긋나기 쉽다.

- [ ] **Step 1: 펌웨어 전체 교체**

`hardware/four_servo_control/four_servo_control.ino` 의 내용을 아래로 교체한다.
`angleToPulse`, `moveServo`, `SERVO_CH`, `HOME_ANGLE`, `MOVE_ANGLE`, `moved[]` 는
기존 값 그대로다. 바뀌는 것은 `loop()` 와 `setup()` 의 출력부뿐이다.

```cpp
#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver();

#define NUM_SERVOS 4
const int SERVO_CH[NUM_SERVOS] = {1, 3, 5, 7};  // 타일 0~3 이 연결된 PCA9685 채널

// 일반적인 서보 기준값 (필요시 미세조정)
#define SERVO_MIN  102    // 약 0도, 0.5ms 펄스
#define SERVO_MAX  512    // 약 180도, 2.5ms 펄스

#define HOME_ANGLE   0     // 초기/복귀 위치
#define MOVE_ANGLE  60     // 작동 위치

bool moved[NUM_SERVOS] = {false, false, false, false};

// 줄 단위 프로토콜용 입력 버퍼
#define BUF_SIZE 64
char buf[BUF_SIZE];
int bufLen = 0;

int angleToPulse(int angle) {
  return map(angle, 0, 180, SERVO_MIN, SERVO_MAX);
}

void moveServo(int index, int angle) {
  pwm.setPWM(SERVO_CH[index], 0, angleToPulse(angle));
}

bool isAllDigits(const char *s) {
  if (*s == '\0') return false;
  for (const char *p = s; *p; p++) {
    if (*p < '0' || *p > '9') return false;
  }
  return true;
}

// "0,2,3" 형식의 인자를 받아 해당 타일을 동시에 작동시킨다.
// 하나라도 잘못된 값이 있으면 아무것도 움직이지 않고 ERR 을 반환한다.
void handleFire(char *args) {
  int wanted[NUM_SERVOS];
  int count = 0;

  char *token = strtok(args, ",");
  while (token != NULL) {
    while (*token == ' ') token++;
    if (!isAllDigits(token)) {
      Serial.println("ERR non-numeric tile");
      return;
    }
    int idx = atoi(token);
    if (idx < 0 || idx >= NUM_SERVOS) {
      Serial.println("ERR tile out of range");
      return;
    }
    if (count >= NUM_SERVOS) {
      Serial.println("ERR too many tiles");
      return;
    }
    wanted[count++] = idx;
    token = strtok(NULL, ",");
  }

  if (count == 0) {
    Serial.println("ERR no tiles");
    return;
  }

  for (int i = 0; i < count; i++) {
    moveServo(wanted[i], MOVE_ANGLE);
    moved[wanted[i]] = true;
  }

  // 받은 인자를 그대로 되돌려준다. 파이썬이 "보낸 것"과 아두이노가 "이해한 것"의
  // 일치를 확인할 수 있어야 한다.
  Serial.print("OK FIRE ");
  for (int i = 0; i < count; i++) {
    if (i > 0) Serial.print(",");
    Serial.print(wanted[i]);
  }
  Serial.println();
}

void handleReset() {
  for (int i = 0; i < NUM_SERVOS; i++) {
    if (moved[i]) {
      moveServo(i, HOME_ANGLE);
      moved[i] = false;
    }
  }
  Serial.println("OK RESET");
}

void handleLine(char *line) {
  if (line[0] == '\0') return;

  if (strncmp(line, "FIRE", 4) == 0 && (line[4] == ' ' || line[4] == '\0')) {
    char *args = line + 4;
    while (*args == ' ') args++;
    handleFire(args);
  } else if (strcmp(line, "RESET") == 0) {
    handleReset();
  } else if (strcmp(line, "PING") == 0) {
    Serial.println("OK PING");
  } else {
    Serial.print("ERR unknown command: ");
    Serial.println(line);
  }
}

void setup() {
  Serial.begin(115200);
  pwm.begin();
  pwm.setPWMFreq(50);   // 서보는 50Hz
  delay(500);

  for (int i = 0; i < NUM_SERVOS; i++) {
    moveServo(i, HOME_ANGLE);
  }

  // '#' 로 시작하는 줄은 파이썬 파서가 무시한다. 사람이 읽을 안내문을 남겨도 된다.
  Serial.println("# 초기화 완료. 타일 0~3 모두 HOME_ANGLE 로 고정.");
  Serial.println("# 명령: FIRE 0,2 / RESET / PING");
  Serial.print("READY ");
  Serial.println(NUM_SERVOS);
}

void loop() {
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      buf[bufLen] = '\0';
      handleLine(buf);
      bufLen = 0;
    } else if (bufLen < BUF_SIZE - 1) {
      buf[bufLen++] = c;
    }
  }
}
```

- [ ] **Step 2: 컴파일 검증 (보드 불필요)**

Arduino IDE에서 이 스케치를 열고 보드 종류만 선택한 뒤 **검증(Verify, ✓ 버튼)** 을
누른다. 업로드가 아니라 컴파일만 하는 것이므로 보드가 연결돼 있지 않아도 된다.

Expected: "컴파일 완료" — 오류 없음

`strtok`, `strncmp`, `strcmp`, `atoi` 는 Arduino 코어에 포함된 `<string.h>`,
`<stdlib.h>` 에 있으므로 추가 `#include` 는 필요 없다. 컴파일 오류가 나면
그 함수들이 선언되지 않은 경우이므로 파일 상단에 `#include <string.h>` 를 더한다.

- [ ] **Step 3: 커밋**

```bash
git add hardware/four_servo_control/four_servo_control.ino
git commit -m "feat: replace single-char servo protocol with line-based text protocol"
```

---

## Task 5b: 펌웨어 하드웨어 검증 (아두이노 확보 후 수행)

**Files:** 없음 (코드 변경 없음. 검증 전용 태스크)

**전제:** Task 5a 완료, 아두이노 + PCA9685 + 서보 4개 + 외부 5V 어댑터가 배선된 상태

**이 태스크는 자동 테스트가 없다.** 시리얼 모니터로 수동 검증한다.
**설계 문서의 가정 A2(4개 동시 기동 전원)가 여기서 판별된다.**

- [ ] **Step 1: 보드에 업로드**

Arduino IDE에서 보드와 포트를 선택하고 업로드한다.

- [ ] **Step 2: 시리얼 모니터로 수동 검증**

Arduino IDE 시리얼 모니터를 **115200 baud, 줄 끝 "새 줄(Newline)"** 로 설정하고
아래를 순서대로 입력해 응답을 확인한다.

| 입력 | 기대 응답 | 확인할 것 |
|---|---|---|
| (보드 리셋 직후) | `# 초기화 완료...` 2줄 후 `READY 4` | 부팅 메시지 |
| `PING` | `OK PING` | |
| `FIRE 1,3` | `OK FIRE 1,3` | 서보 2개가 동시에 움직임 |
| `RESET` | `OK RESET` | 두 서보가 원위치 |
| `FIRE 2` | `OK FIRE 2` | 서보 1개 |
| `RESET` | `OK RESET` | |
| **`FIRE 0,1,2,3`** | `OK FIRE 0,1,2,3` | **가정 A2 검증 — 4개 동시 기동에 보드가 리셋되지 않는지** |
| `RESET` | `OK RESET` | |
| `FIRE 9` | `ERR tile out of range` | 서보는 움직이지 않아야 함 |
| `FIRE` | `ERR no tiles` | 크래시하지 않아야 함 |
| `FIRE abc` | `ERR non-numeric tile` | |
| `HELLO` | `ERR unknown command: HELLO` | |

**`FIRE 0,1,2,3` 을 반드시 수행한다.** 어댑터 용량이 부족하면 여기서 보드가
리셋된다(부팅 메시지가 다시 출력됨). 지금 발견하면 어댑터를 바꾸면 되지만
시연 당일에 발견하면 복구할 수 없다.

- [ ] **Step 3: 서보 이동 시간 측정**

`FIRE 0` 을 입력하는 순간부터 서보가 `MOVE_ANGLE`(60도)에 도달할 때까지의 시간을
휴대폰 슬로모로 촬영해 측정하고, 아래 형식으로 기록해 둔다.

```
서보 HOME(0도) -> MOVE(60도) 이동 시간: ___ ms
```

인형은 약 0.3초 만에 쓰러진다. 이동 시간이 이에 근접하면 "낙상 직전 예측"이
시각적으로 성립하지 않으므로 시연 서사를 조정해야 한다(설계 문서 §10.2).

- [ ] **Step 4: 파이썬과의 연동 확인**

```bash
cd /Users/Yeon/Desktop/fall_detection_DL && python -c "
import tile_protocol
c = tile_protocol.TileController()
print('서보 개수:', c.connect('/dev/cu.usbmodemXXXX'))
print('ping:', c.ping())
print('fire:', c.fire({1, 3}))
print('reset:', c.reset())
c.close()
"
```

`/dev/cu.usbmodemXXXX` 는 실제 포트로 바꾼다. 목록은 `ls /dev/cu.usbmodem*` 로 본다.

Expected:
```
서보 개수: 4
ping: True
fire: True
reset: True
```

`fire: False` 가 나오면 파이썬이 보낸 문자열과 `.ino` 가 되돌려주는 문자열이
어긋난 것이다. 콘솔에 `예상과 다른 응답 ...` 경고가 함께 출력되므로 양쪽을 대조한다.

- [ ] **Step 5: 검증 결과를 설계 문서에 반영**

`docs/superpowers/specs/2026-07-22-multi-tile-activation-design.md` §3의 가정 A2
행에서 "**미검증**" 을 실제 결과로 바꾸고, §13 미해결 사항 표에서 해당 행과
"서보 이동 시간" 행을 갱신한다.

```bash
git add docs/superpowers/specs/2026-07-22-multi-tile-activation-design.md
git commit -m "docs: record hardware verification results for assumption A2"
```

---

## Task 6: 프로파일 설정

인형은 사람보다 약 2.4배 빠르게 쓰러진다(역진자 각속도 ∝ √(g/L)). 판정
파라미터를 대상별로 분리해 설정 파일에 둔다. 코드 상수를 고쳐가며 리허설하면
시연 당일에 잘못된 값이 남는다.

**Files:**
- Create: `config.py`
- Create: `profiles.json`
- Create: `tests/test_config.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `config.Profile` — `name`, `persistence`, `prob_threshold`, `tau_R`, `tau_R_strict`, `tau_lean`, `window` 속성을 가진 데이터클래스
  - `config.load_profile(name, path="profiles.json") -> Profile`
    — 파일이 없거나 이름이 없으면 `ValueError`. `tau_R > tau_R_strict` 이면 `ValueError`.
  - `config.DEFAULT_PROFILE = "human"`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_config.py` 를 새로 만든다:

```python
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
```

- [ ] **Step 2: 테스트를 실행해 실패를 확인**

```bash
cd /Users/Yeon/Desktop/fall_detection_DL && python -m pytest tests/test_config.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'config'`

- [ ] **Step 3: profiles.json 작성**

`profiles.json` 을 새로 만든다:

```json
{
  "human": {
    "persistence": 3,
    "prob_threshold": 0.70,
    "tau_R": 0.85,
    "tau_R_strict": 0.95,
    "tau_lean": 0.15,
    "window": 8
  },
  "doll": {
    "persistence": 2,
    "prob_threshold": 0.60,
    "tau_R": 0.80,
    "tau_R_strict": 0.93,
    "tau_lean": 0.12,
    "window": 6
  }
}
```

- [ ] **Step 4: config.py 작성**

`config.py` 를 새로 만든다:

```python
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
```

- [ ] **Step 5: 테스트를 실행해 통과를 확인**

```bash
cd /Users/Yeon/Desktop/fall_detection_DL && python -m pytest tests/test_config.py -v
```

Expected: PASS — 6 passed

- [ ] **Step 6: 커밋**

```bash
git add config.py profiles.json tests/test_config.py
git commit -m "feat: add per-target detection parameter profiles"
```

---

## Task 7: 캘리브레이션 모듈 분리

`main.py` 에서 호모그래피 관련 코드를 옮기고 `camera_yaw_deg` 를 추가한다.
동작은 그대로다.

**Files:**
- Create: `calibration.py`
- Modify: `main.py:99-153` (해당 함수들을 삭제)
- Modify: `calibrate.py:71-73` (`camera_yaw_deg` 기록)
- Modify: `README.md`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `calibration.CALIBRATION_FILE = "calibration.json"`
  - `calibration.load_tile_grid(path=CALIBRATION_FILE) -> dict | None`
    — 키: `rows`, `cols`, `camera_yaw_deg`, `homography`, `inverse_homography`
  - `calibration.pixel_to_tile(foot_xy, tile_grid) -> tuple[int, int, int]` — `(row, col, tile_index)`
  - `calibration.draw_tile_grid(frame, tile_grid, active_tiles=None) -> None`
    — `active_tiles` 는 강조할 타일 번호의 집합 또는 `None`

- [ ] **Step 1: calibration.py 작성**

`calibration.py` 를 새로 만든다:

```python
"""바닥 타일 격자의 호모그래피 캘리브레이션.

calibrate.py 가 저장한 calibration.json 을 읽어 픽셀 좌표와 격자 셀 사이를
변환한다. main.py 에서 그대로 옮겨온 코드이며, camera_yaw_deg 만 새로 읽는다.
"""

import json
import os

import cv2
import numpy as np

CALIBRATION_FILE = "calibration.json"


def load_tile_grid(path=CALIBRATION_FILE):
    """캘리브레이션을 읽어 격자 정보를 반환한다. 파일이 없으면 None."""
    if not os.path.isfile(path):
        print(f"경고: {path} 가 없습니다 - calibrate.py 를 먼저 실행하세요. "
              "격자 오버레이 없이 진행합니다.")
        return None

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    src = np.array(data["floor_corners_px"], dtype=np.float32)
    dst = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float32)
    homography = cv2.getPerspectiveTransform(src, dst)

    return {
        "rows": data["rows"],
        "cols": data["cols"],
        # 카메라 광축과 타일 격자 축의 각도 차이. 정면이면 0.
        "camera_yaw_deg": float(data.get("camera_yaw_deg", 0.0)),
        "homography": homography,
        "inverse_homography": np.linalg.inv(homography),
    }


def pixel_to_tile(foot_xy, tile_grid):
    """발 위치 픽셀 좌표를 (row, col, tile_index) 로 변환한다."""
    px = np.array([[foot_xy]], dtype=np.float32)
    u, v = cv2.perspectiveTransform(px, tile_grid["homography"])[0][0]
    u = min(max(u, 0.0), 0.999)
    v = min(max(v, 0.0), 0.999)
    col = int(u * tile_grid["cols"])
    row = int(v * tile_grid["rows"])
    return row, col, row * tile_grid["cols"] + col


def draw_tile_grid(frame, tile_grid, active_tiles=None):
    """프레임 위에 격자를 그리고 active_tiles 를 붉게 강조한다."""
    rows, cols = tile_grid["rows"], tile_grid["cols"]
    inv_h = tile_grid["inverse_homography"]

    def floor_to_px(u, v):
        pt = cv2.perspectiveTransform(np.array([[[u, v]]], dtype=np.float32), inv_h)[0][0]
        return int(pt[0]), int(pt[1])

    if active_tiles:
        overlay = frame.copy()
        for tile_index in active_tiles:
            row, col = divmod(tile_index, cols)
            corners = np.array([
                floor_to_px(col / cols, row / rows),
                floor_to_px((col + 1) / cols, row / rows),
                floor_to_px((col + 1) / cols, (row + 1) / rows),
                floor_to_px(col / cols, (row + 1) / rows),
            ], dtype=np.int32).reshape(-1, 1, 2)
            cv2.fillPoly(overlay, [corners], (0, 0, 255))
        cv2.addWeighted(overlay, 0.35, frame, 0.65, 0, dst=frame)

    for r in range(rows + 1):
        v = r / rows
        cv2.line(frame, floor_to_px(0, v), floor_to_px(1, v), (255, 200, 0), 1)
    for c in range(cols + 1):
        u = c / cols
        cv2.line(frame, floor_to_px(u, 0), floor_to_px(u, 1), (255, 200, 0), 1)
```

- [ ] **Step 2: main.py 에서 옮겨온 함수들을 삭제**

`main.py` 에서 아래 네 가지를 삭제한다. Task 9에서 `main.py` 를 재작성하므로
지금은 삭제만 한다.

- `CALIBRATION_FILE = "calibration.json"` 상수 (`main.py:30`)
- `load_tile_grid()` 함수 (`main.py:99-114`)
- `pixelToTile()` 함수 (`main.py:117-125`)
- `drawTileGrid()` 함수 (`main.py:128-152`)

그리고 `main.py` 상단에 임포트를 추가한다:

```python
import calibration
```

호출부를 새 이름으로 바꾼다:

- `tile_grid = load_tile_grid()` → `tile_grid = calibration.load_tile_grid()`
- `pixelToTile(foot_xy, tile_grid)` → `calibration.pixel_to_tile(foot_xy, tile_grid)`
- `drawTileGrid(modified_frame, tile_grid, current_row, current_col)`
  → `calibration.draw_tile_grid(modified_frame, tile_grid, {current_tile} if current_row is not None else None)`

- [ ] **Step 3: calibrate.py 가 camera_yaw_deg 를 기록하도록 수정**

`calibrate.py` 의 마지막 저장 부분(`calibrate.py:71-73`)을 아래로 교체한다:

```python
    with open(CALIBRATION_FILE, "w") as f:
        json.dump({
            "rows": rows,
            "cols": cols,
            "floor_corners_px": points,
            # 카메라 광축과 타일 격자 축의 각도 차이(도). 카메라가 격자를 정면으로
            # 보고 있으면 0. 격자가 시계방향으로 돌아 보이면 양수를 넣는다.
            "camera_yaw_deg": 0.0,
        }, f, indent=2)
    print(f"Saved calibration ({rows}x{cols} grid, {rows * cols} tiles) to {CALIBRATION_FILE}")
    print("카메라가 격자를 정면에서 보고 있지 않다면 calibration.json 의 "
          "camera_yaw_deg 를 손으로 조정하세요.")
```

- [ ] **Step 4: 기존 파이프라인이 그대로 도는지 확인**

```bash
cd /Users/Yeon/Desktop/fall_detection_DL && python main.py test_videos/S01T13R01_.mp4
```

Expected: 기존과 동일하게 동작한다. 창이 뜨고 스켈레톤이 그려지며, ESC로 종료된다.
`calibration.json` 이 없으면 경고가 뜨고 격자 없이 진행된다.

- [ ] **Step 5: README 의 캘리브레이션 절을 갱신**

`README.md` 의 "Per-tile targeting" 절 끝(현재 43행 뒤)에 아래를 추가한다:

```markdown
`calibration.json` 에는 `camera_yaw_deg` 항목이 함께 저장됩니다. 카메라가 타일
격자를 정면에서 보고 있으면 `0` 그대로 두고, 격자가 화면상 회전해 보이면 그
각도(도, 시계방향 양수)를 손으로 넣습니다. 낙상 방향을 격자 좌표계로 옮길 때
사용됩니다.
```

- [ ] **Step 6: 커밋**

```bash
git add calibration.py calibrate.py main.py README.md
git commit -m "refactor: extract tile grid calibration into its own module"
```

---

## Task 8: 카메라 입력 어댑터 분리

`main.py` 의 포즈 추정·특징 계산·모델 추론을 `pose_source.py` 로 옮긴다.
**모델 입력 특징 `[vy, vx, tilt, tilt_vel]` 의 계산 방식은 한 글자도 바꾸지 않는다.**
바꾸면 학습/서빙 불일치가 생긴다.

**Files:**
- Create: `pose_source.py`
- Modify: `main.py` (해당 코드 삭제 — Task 9에서 재작성)

**Interfaces:**
- Consumes: `tiles.lean_from_landmarks`, `calibration.pixel_to_tile`
- Produces:
  - `pose_source.PoseFrame` — 데이터클래스. 필드:
    `image`(numpy 배열), `landmarks`(list 또는 None), `timestamp`(float),
    `risk_score`(float), `is_risky`(bool),
    `direction_deg`(float 또는 None), `lean_ratio`(float 또는 None),
    `foot_tile`(int 또는 None), `face_name`(str)
  - `pose_source.load_risk_model(path="fall_risk_model.joblib") -> dict | None`
  - `pose_source.PoseSource(video_source, model_bundle, prob_threshold, tile_grid=None, face_every=0, face_recognizer=None)`
    — `face_recognizer` 는 `recognize_face(frame) -> str | None` 을 가진 객체 또는 `None`
  - `PoseSource.frames()` — `PoseFrame` 을 순차적으로 내놓는 제너레이터
  - `PoseSource.release() -> None`

- [ ] **Step 1: pose_source.py 작성**

`pose_source.py` 를 새로 만든다:

```python
"""카메라/영상 입력 어댑터.

프레임을 읽어 포즈를 추정하고, 학습된 분류기로 낙상 위험도를 계산하고,
몸통 기울기에서 낙상 방향을 뽑아 PoseFrame 으로 내놓는다.

모델 입력 특징 [vy, vx, tilt, tilt_vel] 의 계산 방식은 main.py 에 있던 것을
그대로 옮긴 것이다. model_training/extract_features.py 와 반드시 일치해야 하며,
바꾸면 학습/서빙 불일치가 발생한다.
"""

import math
import os
from collections import deque
from dataclasses import dataclass
from time import time

import cv2
import joblib
import mediapipe as mp
import numpy as np

import calibration
import tiles

SMOOTHING_WINDOW = 3        # 랜드마크 지터를 줄이려고 평균낼 프레임 수
VELOCITY_THRESHOLD = 1.2    # 모델 파일이 없을 때만 쓰는 옛 단일 임계값

L_SHOULDER, R_SHOULDER = 11, 12
L_HIP, R_HIP = 23, 24
L_ANKLE, R_ANKLE = 27, 28


@dataclass
class PoseFrame:
    image: "np.ndarray"
    landmarks: list
    timestamp: float
    risk_score: float
    is_risky: bool
    direction_deg: float
    lean_ratio: float
    foot_tile: int
    face_name: str


def load_risk_model(path="fall_risk_model.joblib"):
    if not os.path.isfile(path):
        print(f"경고: {path} 가 없습니다 - 단일 수직속도 임계값"
              f"({VELOCITY_THRESHOLD})으로 대체합니다.")
        return None
    bundle = joblib.load(path)
    print(f"낙상 위험 모델 로드됨 (threshold={bundle['prob_threshold']}, "
          f"persistence={bundle['persistence']})")
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


def foot_position(landmarks):
    """양 발목의 중점. 격자 오버레이 표시에만 쓴다 - 타일 선택에는 쓰지 않는다."""
    return _midpoint(landmarks, L_ANKLE, R_ANKLE)


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

    def _detect_pose(self, frame):
        drawn = frame.copy()
        results = self._pose.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        if not results.pose_landmarks:
            return drawn, None

        height, width, _ = frame.shape
        landmarks = [
            (int(lm.x * width), int(lm.y * height), lm.z * width)
            for lm in results.pose_landmarks.landmark
        ]
        for start, end in mp.solutions.pose.POSE_CONNECTIONS:
            cv2.line(drawn,
                     (landmarks[start][0], landmarks[start][1]),
                     (landmarks[end][0], landmarks[end][1]), (0, 255, 0), 3)
        return drawn, landmarks

    def _reset_history(self):
        """추적을 놓쳤을 때 오래된 운동 정보가 다음 낙상에 섞이지 않게 비운다."""
        self._vy_hist.clear()
        self._vx_hist.clear()
        self._prev_center = None
        self._prev_tilt = None
        self._prev_time = None

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
            image, landmarks = self._detect_pose(frame)
            face_name = self._maybe_recognize_face(frame)
            now = self._now()

            if landmarks is None:
                self._reset_history()
                yield PoseFrame(image=image, landmarks=None, timestamp=now,
                                risk_score=0.0, is_risky=False,
                                direction_deg=None, lean_ratio=None,
                                foot_tile=None, face_name=face_name)
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

            if self.model_bundle is not None:
                risk_score = self.model_bundle["model"].predict_proba(
                    [[vy, vx, tilt, tilt_vel]])[0][1]
                is_risky = risk_score >= self.prob_threshold
            else:
                risk_score = vy
                is_risky = vy > VELOCITY_THRESHOLD

            direction_deg, lean_ratio = tiles.lean_from_landmarks(
                landmarks, self.camera_yaw_deg)

            foot_tile = None
            if self.tile_grid is not None:
                _, _, foot_tile = calibration.pixel_to_tile(
                    foot_position(landmarks), self.tile_grid)

            self._prev_center = center
            self._prev_tilt = tilt
            self._prev_time = now

            yield PoseFrame(image=image, landmarks=landmarks, timestamp=now,
                            risk_score=float(risk_score), is_risky=bool(is_risky),
                            direction_deg=direction_deg, lean_ratio=lean_ratio,
                            foot_tile=foot_tile, face_name=face_name)

    def release(self):
        self._video.release()
```

- [ ] **Step 2: 임포트가 깨지지 않는지 확인**

```bash
cd /Users/Yeon/Desktop/fall_detection_DL && python -c "import pose_source; print('ok')"
```

Expected: `ok` (mediapipe 로딩 경고가 함께 출력될 수 있다)

- [ ] **Step 3: 특징 계산이 바뀌지 않았는지 눈으로 대조**

`main.py:268-290` 의 원본 특징 계산과 `pose_source.py` 의 `frames()` 안 계산을
나란히 놓고 확인한다. 아래 네 가지가 원본과 동일해야 한다.

- `vy = (center[1] - prev_center[1]) / height / dt`
- `vx = (center[0] - prev_center[0]) / width / dt`
- `SMOOTHING_WINDOW = 3` 크기 deque 의 산술평균
- `predict_proba([[vy, vx, tilt, tilt_vel]])[0][1]` — **인자 순서**

- [ ] **Step 4: 커밋**

```bash
git add pose_source.py
git commit -m "refactor: extract camera pose adapter with fall direction output"
```

---

## Task 9: main.py 조립 — CLI, 발사 상태 기계, 로깅

**Files:**
- Modify: `main.py` (전체 교체)
- Modify: `README.md`

**Interfaces:**
- Consumes: `tiles`, `tile_protocol`, `config`, `calibration`, `pose_source` 전부
- Produces: 실행 가능한 CLI

- [ ] **Step 1: main.py 전체 교체**

`main.py` 의 내용을 아래로 교체한다:

```python
"""낙상 직전 감지 -> 방향 판정 -> 멀티 타일 작동.

사용법:
    python main.py                                    웹캠
    python main.py test_videos/S01T13R01_.mp4         녹화 영상
    python main.py --port /dev/cu.usbmodemXXXX        아두이노 연결
    python main.py --profile doll                     인형 프로파일
    python main.py --no-serial                        임계값 튜닝용 (서보 안 움직임)
"""

import argparse
import csv
import os
import sys
from collections import deque
from datetime import datetime

import cv2

import calibration
import config
import pose_source
import tile_protocol
import tiles

RISK_COOLDOWN = 3.0    # 같은 낙상에 대해 다시 발사하기까지 기다리는 시간(초)
RESET_DELAY = 2.0      # 발사 후 원위치 신호를 보내기까지의 시간(초)
LOG_FILE = "fall_risk_log.csv"

LOG_HEADER = ["timestamp", "person", "risk_score", "direction_deg",
              "lean_ratio", "R", "tier", "fired_tiles", "ack", "profile"]


def parse_args():
    parser = argparse.ArgumentParser(description="낙상 직전 감지 및 멀티 타일 작동")
    parser.add_argument("video_source", nargs="?", default="0",
                        help="웹캠 인덱스(기본 0) 또는 영상 파일 경로")
    parser.add_argument("--port", default=None,
                        help="아두이노 시리얼 포트. 생략하면 시뮬레이션 모드")
    parser.add_argument("--profile", default=config.DEFAULT_PROFILE,
                        help="profiles.json 의 프로파일 이름 (human / doll)")
    parser.add_argument("--no-serial", action="store_true",
                        help="시리얼을 쓰지 않는다. 임계값 튜닝용")
    parser.add_argument("--face-every", type=int, default=0,
                        help="N프레임마다 얼굴 인식. 0이면 비활성(기본). "
                             "얼굴 인식은 느려서 fps 를 크게 떨어뜨린다")
    return parser.parse_args()


def log_event(profile_name, person, risk_score, direction_deg, lean_ratio,
              R, fired_tiles, ack):
    is_new = not os.path.isfile(LOG_FILE)
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(LOG_HEADER)
        writer.writerow([
            datetime.now().isoformat(timespec="seconds"),
            person,
            f"{risk_score:.3f}",
            f"{direction_deg:.1f}",
            f"{lean_ratio:.3f}",
            f"{R:.3f}",
            len(fired_tiles),
            "|".join(str(t) for t in sorted(fired_tiles)),
            int(bool(ack)),
            profile_name,
        ])


def build_face_recognizer(face_every):
    if face_every <= 0:
        return None
    import facial_recognition as fr

    recognizer = fr.FaceRecognition()
    recognizer.encode_faces()
    return recognizer


def main():
    args = parse_args()

    try:
        profile = config.load_profile(args.profile)
    except ValueError as exc:
        print(f"오류: {exc}")
        return 1
    print(f"프로파일 '{profile.name}' - persistence={profile.persistence}, "
          f"tau_R={profile.tau_R}, tau_R_strict={profile.tau_R_strict}, "
          f"tau_lean={profile.tau_lean}, window={profile.window}")

    video_source = int(args.video_source) if args.video_source.isdigit() else args.video_source

    tile_grid = calibration.load_tile_grid()
    rows = tile_grid["rows"] if tile_grid else 2
    cols = tile_grid["cols"] if tile_grid else 2

    controller = tile_protocol.TileController()
    if not args.no_serial:
        servo_count = controller.connect(args.port)
        if servo_count and servo_count != rows * cols:
            print(f"경고: 펌웨어 서보 {servo_count}개 vs 캘리브레이션 "
                  f"{rows}x{cols}={rows * cols}개 - 설정이 어긋났습니다.")
    else:
        print("--no-serial: 서보를 움직이지 않고 로그만 남깁니다.")

    model_bundle = pose_source.load_risk_model()
    prob_threshold = profile.prob_threshold
    persistence = profile.persistence

    source = pose_source.PoseSource(
        video_source=video_source,
        model_bundle=model_bundle,
        prob_threshold=prob_threshold,
        tile_grid=tile_grid,
        face_every=args.face_every,
        face_recognizer=build_face_recognizer(args.face_every),
    )

    window = deque(maxlen=profile.window)
    consecutive_risk_frames = 0
    last_risk_time = -RISK_COOLDOWN
    reset_pending = False
    active_tiles = set()

    for frame in source.frames():
        now = frame.timestamp

        if frame.landmarks is None:
            # 추적 상실 - 오래된 방향이 다음 낙상 판정에 섞이면 안 된다
            window.clear()
            consecutive_risk_frames = 0
        else:
            window.append((frame.direction_deg, frame.lean_ratio))
            consecutive_risk_frames = consecutive_risk_frames + 1 if frame.is_risky else 0

        if (consecutive_risk_frames >= persistence
                and (now - last_risk_time) > RISK_COOLDOWN):
            direction_deg, R, lean_ratio = tiles.resolve_direction(window)
            fired = tiles.select_tiles(
                direction_deg, R, lean_ratio, rows, cols,
                profile.tau_R, profile.tau_R_strict, profile.tau_lean)

            ack = False if args.no_serial else controller.fire(fired)
            print(f"[낙상 위험] score={frame.risk_score:.2f} "
                  f"dir={direction_deg:.1f}도 R={R:.2f} lean={lean_ratio:.2f} "
                  f"-> 타일 {sorted(fired)} ({len(fired)}장) ack={ack}")
            log_event(profile.name, frame.face_name, frame.risk_score,
                      direction_deg, lean_ratio, R, fired, ack)

            active_tiles = fired
            last_risk_time = now
            consecutive_risk_frames = 0
            reset_pending = True

        if reset_pending and (now - last_risk_time) > RESET_DELAY:
            if not args.no_serial:
                controller.reset()
            reset_pending = False
            active_tiles = set()

        image = frame.image
        if tile_grid is not None:
            calibration.draw_tile_grid(image, tile_grid, active_tiles)

        cv2.putText(image,
                    f"risk {frame.risk_score:.2f} "
                    f"({consecutive_risk_frames}/{persistence})",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        if frame.direction_deg is not None:
            cv2.putText(image,
                        f"dir {frame.direction_deg:.0f} lean {frame.lean_ratio:.2f}",
                        (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2)
        if controller.simulated and not args.no_serial:
            cv2.putText(image, "NO ARDUINO (simulated)", (10, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

        cv2.imshow("Fall Detection", image)
        if (cv2.waitKey(1) & 0xFF) == 27:
            break

    source.release()
    cv2.destroyAllWindows()
    controller.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 하드웨어 없이 녹화 영상으로 전체 파이프라인 확인**

```bash
cd /Users/Yeon/Desktop/fall_detection_DL && python main.py test_videos/S01T13R01_.mp4 --no-serial
```

Expected:
- 프로파일 로드 메시지가 출력된다
- 창이 뜨고 스켈레톤과 `risk`, `dir`, `lean` 값이 표시된다
- 낙상 구간에서 `[낙상 위험] ... -> 타일 [...] (N장)` 이 출력된다
- ESC로 종료된다

- [ ] **Step 3: 로그 컬럼이 제대로 기록됐는지 확인**

```bash
cd /Users/Yeon/Desktop/fall_detection_DL && head -3 fall_risk_log.csv
```

Expected: 헤더가 `timestamp,person,risk_score,direction_deg,lean_ratio,R,tier,fired_tiles,ack,profile` 이고 데이터 행이 있다.

**주의:** 기존 `fall_risk_log.csv` 에는 옛 컬럼(`tile`)의 데이터가 남아 있다.
새 헤더와 섞이므로 확인 전에 옮겨둔다:

```bash
mv fall_risk_log.csv fall_risk_log.old.csv
```

- [ ] **Step 4: 전체 테스트를 다시 실행**

```bash
cd /Users/Yeon/Desktop/fall_detection_DL && python -m pytest tests/ -v
```

Expected: 전부 PASS

- [ ] **Step 5: README 갱신**

`README.md` 의 "Usage" 절(현재 20-25행)을 아래로 교체한다:

````markdown
## Usage

```
python main.py                                  # 웹캠
python main.py test_videos/S01T13R01_.mp4       # 녹화 영상
python main.py --port /dev/cu.usbmodemXXXX      # 아두이노 연결
python main.py --profile doll                   # 인형 프로파일
python main.py --no-serial                      # 임계값 튜닝용 (서보 안 움직임)
python main.py --face-every 10                  # 10프레임마다 얼굴 인식
```

얼굴 인식은 기본으로 꺼져 있습니다(`--face-every 0`). `face_recognition` 은 무거워서
프레임레이트를 크게 떨어뜨리고, 프레임레이트가 떨어지면 빠르게 쓰러지는 대상에서
`persistence` 프레임 수를 채우지 못합니다.

### 판정 프로파일

낙상 판정 파라미터는 `profiles.json` 에 있습니다. 코드 상수로 두지 않는 이유는
리허설 중에 코드를 고치면 시연 당일 잘못된 값이 남기 때문입니다.

| 항목 | 뜻 |
|---|---|
| `persistence` | 발사하기까지 필요한 연속 위험 프레임 수 |
| `prob_threshold` | 낙상 위험으로 볼 모델 확률 |
| `window` | 방향 평균을 낼 프레임 수 |
| `tau_R` | 이 값 미만이면 방향 판정 불가 → 전체 타일 |
| `tau_R_strict` | 이 값 이상이고 대각 정중앙이면 모서리 1장만 |
| `tau_lean` | 이 값 미만이면 수직 붕괴로 보고 전체 타일 |

`tau_*` 세 값은 물리 상수가 아니라 연출값입니다. `--no-serial` 로 25~30회
리허설한 뒤 `fall_risk_log.csv` 의 `lean_ratio` 와 `R` 분포를 보고 정합니다.
자세한 절차는 설계 문서 §10.3을 참고하세요.
````

그리고 "Arduino / servo signal" 절(현재 45-52행)을 아래로 교체한다:

````markdown
### 아두이노 / 서보 신호

`--port` 로 시리얼 포트를 지정합니다(예: macOS `/dev/cu.usbmodemXXXX`,
Windows `COM3`). 생략하면 시뮬레이션 모드로 동작하며 신호는 콘솔에만 찍힙니다.

프로토콜은 줄 단위 텍스트이고 보율은 115200입니다.

| 파이썬 → 아두이노 | 아두이노 → 파이썬 |
|---|---|
| `FIRE 1,3` | `OK FIRE 1,3` |
| `RESET` | `OK RESET` |
| `PING` | `OK PING` |
| — | `READY 4` (부팅 완료 시) |
| — | `ERR <사유>` |
| — | `# <주석, 무시됨>` |

타일 번호는 어디서나 0-indexed 입니다. 타일 번호와 PCA9685 채널의 매핑은
`.ino` 안에만 있습니다.

시리얼 모니터(115200, 줄 끝 "새 줄")에서 `FIRE 1,3` 을 직접 입력하면 파이썬 없이
하드웨어만 시험할 수 있습니다. 서보 4개 동시 기동은 `FIRE 0,1,2,3` 으로
확인하세요 — 전원 용량이 부족하면 보드가 리셋됩니다.
````

- [ ] **Step 6: 커밋**

```bash
git add main.py README.md
git commit -m "feat: wire multi-tile selection into the main detection loop"
```

---

## Self-Review

**Spec coverage:**

| 설계 문서 절 | 담당 태스크 |
|---|---|
| §5 모듈 구조 | Task 1, 4, 6, 7, 8, 9 |
| §6.1 방향 계산 | Task 1 |
| §6.2 원형 평균, 창 비우기 | Task 2 (함수), Task 9 (창 관리) |
| §6.3 규칙 1·2·3 | Task 3 |
| §6.4 게이트 | Task 3 |
| §6.5 임계값 프로파일, `tau_R <= tau_R_strict` 검증 | Task 6 |
| §6.7 인터페이스 | Task 1, 2, 3 |
| §7.1 문법 | Task 4, 5a |
| §7.2 핸드셰이크, 서보 개수 대조 | Task 4, Task 9 |
| §7.3 보율·타임아웃·비치명적 실패 | Task 4 |
| §7.4 리셋 | Task 5a, Task 9 |
| §7.6 인덱싱 통일, 단일 문자 제거 | Task 5a |
| §7.7 펌웨어 변경 범위 | Task 5a |
| §8 프로파일·CLI·`camera_yaw_deg` | Task 6, 7, 9 |
| §9 로깅 컬럼 | Task 9 |
| §10.1 단위 테스트 | Task 1, 2, 3, 4, 6 |
| §10.2 하드웨어 검증, 서보 이동 시간 | Task 5b |
| §10.3 튜닝 절차 (`--no-serial`) | Task 9 + README |
| §11 시연 사다리 | Task 9 (`--profile` 전환, 영상 재생) |
| §12 구현 순서 | 태스크 번호 순서와 일치 |

**§6.6의 차선책**(앞뒤 판정 포기)은 §10.3의 튜닝 결과를 본 뒤에 결정하는 사항이므로
태스크로 만들지 않았다. 발동 시 `tiles.lean_from_landmarks` 의 `dz` 항만 0으로
두는 국소 변경이다.

**Placeholder scan:** 통과. 모든 코드 단계에 실제 코드가 들어 있고, 모든 명령에
기대 출력이 명시되어 있다.

**Type consistency 확인:**
- `tiles.select_tiles` 의 인자 순서 `(direction_deg, R, lean_ratio, rows, cols, tau_R, tau_R_strict, tau_lean)` — Task 3 정의, Task 9 호출 일치
- `tiles.resolve_direction` 반환 `(direction, R, lean)` — Task 2 정의, Task 9 언패킹 순서 일치
- `TileController.fire(set[int]) -> bool` — Task 4 정의, Task 9 사용 일치
- `calibration.draw_tile_grid(frame, tile_grid, active_tiles)` — Task 7 정의(집합 인자), Task 9 호출 일치
- `pose_source.PoseFrame` 필드명 — Task 8 정의, Task 9 접근 일치
- `config.Profile` 필드명 — Task 6 정의, Task 9 접근 일치
