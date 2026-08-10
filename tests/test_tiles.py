import math

import pytest

import tiles


# --- 방향: 몸통 중심의 화면 이동(vx, vy)에서 뽑는다 ---
# vx: +오른쪽, vy: +아래(화면 좌표). 비스듬히 내려보는 카메라에서 화면 이동
# 방향이 곧 바닥 낙상 방향이다. MediaPipe z(단안 깊이)는 앞/뒤를 못 가려서 쓰지
# 않는다. 규약: 0=먼쪽(화면 위), 90=우, 180=가까움(화면 아래), 270=좌.

def test_motion_right_is_90_degrees():
    assert tiles.direction_from_motion(1.0, 0.0) == pytest.approx(90.0)


def test_motion_down_toward_camera_is_180_degrees():
    # 화면에서 아래로 이동 = 카메라 쪽(가까움)
    assert tiles.direction_from_motion(0.0, 1.0) == pytest.approx(180.0)


def test_motion_up_away_from_camera_is_0_degrees():
    # 화면에서 위로 이동 = 카메라 반대(먼 쪽)
    assert tiles.direction_from_motion(0.0, -1.0) == pytest.approx(0.0)


def test_motion_left_is_270_degrees():
    assert tiles.direction_from_motion(-1.0, 0.0) == pytest.approx(270.0)


def test_motion_diagonal_up_right_is_45_degrees():
    # 오른쪽 + 위(먼쪽) = 먼쪽·우 대각
    assert tiles.direction_from_motion(1.0, -1.0) == pytest.approx(45.0)


def test_motion_diagonal_down_left_is_225_degrees():
    # 왼쪽 + 아래(가까움) = 가까운쪽·좌 대각
    assert tiles.direction_from_motion(-1.0, 1.0) == pytest.approx(225.0)


def test_camera_yaw_rotates_the_direction():
    # 카메라가 격자 대비 90도 돌아가 있으면 "이미지상 우측"이 격자상 0도가 된다
    assert tiles.direction_from_motion(1.0, 0.0, camera_yaw_deg=90.0) == pytest.approx(0.0)


def test_no_motion_returns_degenerate_zero():
    # 정지 상태(속도 ~0)는 방향이 없다. 위험 프레임이 아니므로 창에 들어가지도 않지만
    # 나눗셈 오류 없이 0을 돌려줘야 한다.
    assert tiles.direction_from_motion(0.0, 0.0) == 0.0


def test_lean_from_tilt_upright_is_zero():
    assert tiles.lean_from_tilt(0.0) == pytest.approx(0.0)


def test_lean_from_tilt_horizontal_is_one():
    assert tiles.lean_from_tilt(90.0) == pytest.approx(1.0)


def test_lean_from_tilt_45_degrees():
    assert tiles.lean_from_tilt(45.0) == pytest.approx(math.sqrt(0.5))


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


# --- 한 장으로 줄이기 (배터리 한계) ---

def test_tile_direction_points_at_each_corner_of_a_2x2_grid():
    # 행 우선 번호: 0=먼쪽·좌, 1=먼쪽·우, 2=가까운쪽·좌, 3=가까운쪽·우
    assert tiles.tile_direction_deg(0, 2, 2) == pytest.approx(315.0)
    assert tiles.tile_direction_deg(1, 2, 2) == pytest.approx(45.0)
    assert tiles.tile_direction_deg(2, 2, 2) == pytest.approx(225.0)
    assert tiles.tile_direction_deg(3, 2, 2) == pytest.approx(135.0)


@pytest.mark.parametrize("direction, expected", [
    (45.0, 1),      # 먼쪽·우
    (135.0, 3),     # 가까운쪽·우
    (225.0, 2),     # 가까운쪽·좌
    (315.0, 0),     # 먼쪽·좌
    (341.0, 0),     # 아래는 실제 시연 로그에서 나온 방향들
    (224.8, 2),
    (74.4, 1),
    (277.9, 0),
])
def test_narrow_to_one_follows_the_fall_direction(direction, expected):
    """후보가 4장 전부여도 방향에 맞는 타일이 나와야 한다.

    회귀 테스트다. 예전에는 min(candidates) 로 줄여서 R < tau_R 로 게이트가
    열릴 때마다(= 후보 4장) 방향과 무관하게 항상 0번만 펴졌다.
    """
    assert tiles.narrow_to_one({0, 1, 2, 3}, direction, 2, 2) == {expected}


def test_narrow_to_one_is_not_biased_toward_low_indices():
    """네 방향이 네 타일을 각각 골라야 한다 - 전부 0이면 예전 버그다.

    대각(45/135/225/315)으로 시험하는 이유: 2x2 격자에는 정방향(0/90/180/270)에
    놓인 타일이 없다. 예를 들어 0도(먼 쪽)는 0번과 1번 모서리에서 정확히 45도씩
    떨어져 동점이 되므로, 정방향으로는 편향을 판별할 수 없다.
    """
    chosen = {next(iter(tiles.narrow_to_one({0, 1, 2, 3}, d, 2, 2)))
              for d in (315.0, 45.0, 225.0, 135.0)}
    assert chosen == {0, 1, 2, 3}


def test_narrow_to_one_on_a_cardinal_direction_is_a_tie_between_two_corners():
    # 2x2 에서 0도는 0번·1번과 45도씩 떨어진 진짜 동점이다. 어느 쪽이 나오든
    # 틀린 답은 아니고, 다만 같은 입력에 같은 답이 나오기만 하면 된다.
    assert tiles.narrow_to_one({0, 1, 2, 3}, 0.0, 2, 2) <= {0, 1}
    assert tiles.narrow_to_one({0, 1, 2, 3}, 180.0, 2, 2) <= {2, 3}


def test_narrow_to_one_only_picks_from_the_candidates():
    # 방향은 3번을 가리키지만 후보에 없으면 후보 중에서 골라야 한다
    assert tiles.narrow_to_one({0, 1}, 135.0, 2, 2) <= {0, 1}


def test_narrow_to_one_breaks_ties_deterministically():
    # 정확히 두 타일의 중간을 가리키는 방향 - 늘 같은 답이 나와야 재현이 된다
    first = tiles.narrow_to_one({0, 1}, 0.0, 2, 2)
    assert first == tiles.narrow_to_one({0, 1}, 0.0, 2, 2)
    assert len(first) == 1


def test_narrow_to_one_handles_empty_candidates():
    assert tiles.narrow_to_one(set(), 90.0, 2, 2) == set()


@pytest.mark.parametrize("direction", [d * 7.0 for d in range(52)])
@pytest.mark.parametrize("R", [0.5, 0.86, 0.99])
@pytest.mark.parametrize("lean_ratio", [0.05, 0.4])
def test_narrowing_any_selection_always_yields_exactly_one_valid_tile(
        direction, R, lean_ratio):
    result = tiles.narrow_to_one(pick(direction, R=R, lean_ratio=lean_ratio),
                                 direction, 2, 2)
    assert len(result) == 1
    assert result <= {0, 1, 2, 3}
