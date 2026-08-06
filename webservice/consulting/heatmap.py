"""사람 검출 박스 → 동선(이동 경로) 지도. 순수 함수 — YOLO/torch 의존 없음.

두 가지 지도를 만들 수 있다.

- `accumulate_heatmap` : 박스 전체를 누적하는 **체류(dwell) 지도**. 한 자리에 오래
  서 있을수록 뜨거워진다. 초기 버전에서 쓰던 방식이며 하위 호환으로 남겨둔다.
- `accumulate_passage_map` : 발끝 궤적에서 **가만히 있는 구간을 걷어낸 뒤** 누적하는
  **동선(passage) 지도**. 같은 복도를 세 번 지나가면 세 번 쌓이고, 10초를 서 있어도
  한 번만 쌓인다. 컨설팅 판정은 이쪽을 쓴다.

체류가 아니라 동선을 보는 이유는 rules.py 의 모듈 독스트링을 참고.
"""

import cv2
import numpy as np

# 프레임 대각선 대비 비율로 잡는 기본값들. 픽셀 상수로 두면 해상도가 바뀔 때
# 의미가 달라지므로 전부 상대값이다.
DEFAULT_MIN_STEP_FRAC = 0.02   # 이만큼 못 움직이면 '제자리'로 보고 버린다
DEFAULT_RADIUS_FRAC = 0.035    # 발끝 한 점이 차지하는 바닥 면적의 반지름
DEFAULT_SMOOTH_WINDOW = 5      # 궤적 이동평균 창(프레임)
DEFAULT_MAX_GAP = 3            # 이 프레임 수 이하의 미검출은 보간해서 잇는다


# --------------------------------------------------------------------------
# 궤적 추출
# --------------------------------------------------------------------------

def foot_point(box):
    """바운딩박스 → 사람이 딛고 선 바닥 위치(하단 중앙).

    상자 중심을 쓰면 키 큰 사람과 앉은 사람이 다른 바닥 좌표로 잡힌다. 바닥
    동선을 보려는 것이므로 하단 중앙이 맞다.
    """
    x1, y1, x2, y2 = box
    return ((x1 + x2) / 2.0, float(y2))


def foot_points(boxes_per_frame):
    """프레임별 박스 목록 → 프레임별 발끝 좌표(검출 없으면 None).

    한 프레임에 여러 명이 잡히면 가장 큰 박스를 고른다. 가정 내 촬영에서는
    피사체가 카메라에 가장 크게 잡히고, 배경에 스치는 오검출은 작다.
    """
    out = []
    for boxes in boxes_per_frame:
        if not boxes:
            out.append(None)
            continue
        biggest = max(boxes, key=lambda b: abs(b[2] - b[0]) * abs(b[3] - b[1]))
        out.append(foot_point(biggest))
    return out


def split_segments(points, max_gap=0):
    """None(미검출)을 경계로 궤적을 연속 구간들로 자른다.

    사람이 프레임 밖으로 나갔다 들어오면 그 사이를 직선으로 이으면 안 되므로
    구간을 나눈다.

    다만 검출기는 가려짐·모션블러로 한두 프레임씩 사람을 놓친다. 그때마다
    구간을 끊으면 한 번의 이동이 여러 조각으로 부서지고, 조각마다 첫 점만
    남아 동선이 실제보다 성기게 잡힌다. `max_gap` 프레임 이하의 공백은 앞뒤
    좌표를 선형 보간해 메운다 — 그 사이 사람이 순간이동했을 리는 없으므로
    직선 보간이 실제 경로에 가깝다.
    """
    segments, cur = [], []
    gap = 0
    for p in points:
        if p is None:
            if cur:
                gap += 1
                if gap > max_gap:
                    segments.append(cur)
                    cur = []
                    gap = 0
            continue
        if cur and gap:
            # 공백을 앞뒤 좌표 사이의 직선으로 메운다
            prev = cur[-1]
            for i in range(1, gap + 1):
                t = i / (gap + 1)
                cur.append((prev[0] + (p[0] - prev[0]) * t,
                            prev[1] + (p[1] - prev[1]) * t))
        gap = 0
        cur.append(p)
    if cur:
        segments.append(cur)
    return segments


def smooth_segment(seg, window=DEFAULT_SMOOTH_WINDOW):
    """궤적 한 구간에 이동평균을 걸어 검출 지터를 없앤다.

    스무딩 없이 재샘플링하면, 서 있는 사람의 박스가 프레임마다 몇 픽셀씩
    흔들리는 것만으로 min_step 을 넘겨 '움직였다'고 오판한다.
    """
    n = len(seg)
    if n == 0 or window <= 1:
        return list(seg)
    w = min(window, n)
    half = w // 2
    xs = np.array([p[0] for p in seg], dtype=np.float64)
    ys = np.array([p[1] for p in seg], dtype=np.float64)
    out = []
    for i in range(n):
        lo, hi = max(0, i - half), min(n, i + half + 1)
        out.append((float(xs[lo:hi].mean()), float(ys[lo:hi].mean())))
    return out


def resample_segment(seg, min_step):
    """직전에 남긴 점에서 min_step 이상 떨어진 점만 남긴다.

    **체류를 동선으로 바꾸는 핵심 단계.** 제자리에 머문 프레임들은 전부 첫 점
    하나로 접히고, 걸어간 구간만 경로를 따라 점이 깔린다. 격자에 의존하지 않으므로
    나중에 격자 크기를 바꿔도 판정 의미가 흔들리지 않는다.
    """
    kept = []
    for p in seg:
        if not kept:
            kept.append(p)
            continue
        dx, dy = p[0] - kept[-1][0], p[1] - kept[-1][1]
        if (dx * dx + dy * dy) ** 0.5 >= min_step:
            kept.append(p)
    return kept


def extract_path(boxes_per_frame, height, width,
                 smooth_window=DEFAULT_SMOOTH_WINDOW,
                 min_step_frac=DEFAULT_MIN_STEP_FRAC,
                 max_gap=DEFAULT_MAX_GAP):
    """프레임별 박스 → 스무딩·재샘플링을 마친 동선 구간 목록.

    반환값은 구간들의 리스트이고, 각 구간은 (x, y) 좌표 리스트다. 긴 미검출
    구간에서만 나뉘고, 짧은 공백은 보간해서 잇는다.
    """
    diag = (height ** 2 + width ** 2) ** 0.5
    min_step = diag * min_step_frac
    segments = []
    for seg in split_segments(foot_points(boxes_per_frame), max_gap=max_gap):
        smoothed = smooth_segment(seg, smooth_window)
        resampled = resample_segment(smoothed, min_step)
        if resampled:
            segments.append(resampled)
    return segments


# --------------------------------------------------------------------------
# 누적 지도
# --------------------------------------------------------------------------

def _disc_kernel(radius):
    """반지름 radius 인 원판 커널(내부 1.0). 정규화하지 않는다.

    정규화하면 값이 '단위 면적당 점 밀도'가 되어 읽기 어렵다. 1.0 그대로 두면
    결과 픽셀값이 곧 '이 지점 반경 안을 지나간 경로 점의 개수'가 된다.
    """
    size = 2 * radius + 1
    yy, xx = np.ogrid[-radius:radius + 1, -radius:radius + 1]
    return ((xx * xx + yy * yy) <= radius * radius).astype(np.float32)


def accumulate_passage_map(segments, height, width,
                           radius_frac=DEFAULT_RADIUS_FRAC, blur=31):
    """동선 구간들 → 통행량 지도(float32, height×width).

    경로 점을 임펄스로 찍은 뒤 원판 커널로 한 번 필터링한다. `cv2.circle` 로
    점마다 원을 그리면 **값이 덮어써져서 누적이 안 되고**(같은 자리를 세 번
    지나도 1.0), 점마다 마스크를 새로 만들어 더하면 점 개수에 비례해 느려진다.
    임펄스 + 컨볼루션이 둘 다 피한다 — 결과 픽셀값은 그 지점을 지나간 경로
    점의 개수가 되고, 비용은 점 개수와 무관하다.
    """
    impulses = np.zeros((height, width), dtype=np.float32)
    for seg in segments:
        for (x, y) in seg:
            xi = min(max(int(round(x)), 0), width - 1)
            yi = min(max(int(round(y)), 0), height - 1)
            impulses[yi, xi] += 1.0        # 겹치는 점은 실제로 더해진다

    diag = (height ** 2 + width ** 2) ** 0.5
    radius = max(1, int(round(diag * radius_frac)))
    acc = cv2.filter2D(impulses, -1, _disc_kernel(radius),
                       borderType=cv2.BORDER_CONSTANT)
    k = blur if blur % 2 == 1 else blur + 1
    if k > 1:
        acc = cv2.GaussianBlur(acc, (k, k), 0)   # 경계를 부드럽게(선형이라 총량 보존)
    return acc


def accumulate_heatmap(boxes_per_frame, height, width, blur=51):
    """박스 전체를 누적하는 체류 지도(하위 호환).

    동선 판정에는 `accumulate_passage_map` 을 쓴다. 이 함수는 기존 테스트와
    대조용으로 남아 있다.

    누적은 차분 배열(difference array) + 2D 누적합으로 한다. `cv2.rectangle` 은
    값을 덮어쓰므로 겹치는 박스가 쌓이지 않고, 박스마다 마스크를 새로 만들어
    블러하면 프레임 수에 비례해 느려진다. 차분 배열은 박스당 4번의 덧셈이면
    끝나고, 블러가 선형이라 '박스마다 블러 후 합' 과 결과가 동일하다.
    """
    # 경계 처리를 위해 한 칸 여유를 둔다
    diff = np.zeros((height + 1, width + 1), dtype=np.float32)
    for boxes in boxes_per_frame:
        for (x1, y1, x2, y2) in boxes:
            # cv2.rectangle 은 끝점을 포함하므로 +1 해서 동일 범위를 만든다
            xa = min(max(int(x1), 0), width)
            ya = min(max(int(y1), 0), height)
            xb = min(max(int(x2) + 1, 0), width)
            yb = min(max(int(y2) + 1, 0), height)
            if xb <= xa or yb <= ya:
                continue
            diff[ya, xa] += 1.0
            diff[ya, xb] -= 1.0
            diff[yb, xa] -= 1.0
            diff[yb, xb] += 1.0
    acc = np.cumsum(np.cumsum(diff, axis=0), axis=1)[:height, :width]
    acc = np.ascontiguousarray(acc, dtype=np.float32)
    k = blur if blur % 2 == 1 else blur + 1
    if k > 1:
        acc = cv2.GaussianBlur(acc, (k, k), 0)
    return acc


# --------------------------------------------------------------------------
# 렌더링
# --------------------------------------------------------------------------

def render_heatmap_png(heatmap, out_path, background=None):
    norm = cv2.normalize(heatmap, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    color = cv2.applyColorMap(norm, cv2.COLORMAP_JET)
    if background is not None:
        color = cv2.addWeighted(background, 0.5, color, 0.5, 0)
    cv2.imwrite(out_path, color)


def draw_path(img, segments):
    """방 사진 위에 이동 경로를 선으로 그린다(그 자리에서 수정).

    선 색은 시작(파랑)에서 끝(빨강)으로 변해 진행 방향을 읽을 수 있게 했다.
    흰 테두리를 먼저 깔아 어두운 바닥 위에서도 보이게 한다.
    """
    pts_total = sum(len(s) for s in segments)
    if pts_total == 0:
        return img

    def as_int(p):
        return (int(round(p[0])), int(round(p[1])))

    # 흰 테두리를 먼저 전부 깔고 그 위에 색선을 얹는다. 선분마다 테두리→색선을
    # 번갈아 그리면 다음 선분의 테두리가 직전 색선 끝을 덮어 줄무늬가 생긴다.
    for seg in segments:
        for i in range(len(seg) - 1):
            cv2.line(img, as_int(seg[i]), as_int(seg[i + 1]),
                     (255, 255, 255), 5, cv2.LINE_AA)

    drawn = 0
    for seg in segments:
        for i in range(len(seg) - 1):
            t = drawn / max(pts_total - 1, 1)               # 0 → 1 진행도
            col = (int(255 * (1 - t)), 60, int(255 * t))    # BGR: 파랑 → 빨강
            cv2.line(img, as_int(seg[i]), as_int(seg[i + 1]), col, 3, cv2.LINE_AA)
            drawn += 1
        drawn += 1                                          # 구간 사이 진행도 보정

    for seg in segments:
        if not seg:
            continue
        s, e = as_int(seg[0]), as_int(seg[-1])
        cv2.circle(img, s, 7, (255, 255, 255), -1)
        cv2.circle(img, s, 5, (255, 120, 0), -1)      # 시작점(파랑)
        cv2.circle(img, e, 7, (255, 255, 255), -1)
        cv2.circle(img, e, 5, (0, 60, 255), -1)       # 끝점(빨강)
    return img


def render_hazard_boxes(frame, findings, rows, cols, out_path, segments=None):
    """방 프레임 위에 위험 구역(격자 셀)을 반투명 빨간 박스 + 굵은 테두리로 표시.

    `segments` 를 주면 위험 구역 아래에 이동 경로도 함께 그린다. 경로가 있으면
    '왜 이 구역이 위험한가'(= 자주 지나다닌다)가 그림 한 장으로 설명된다.
    """
    img = frame.copy()
    if segments:
        draw_path(img, segments)
    h, w = img.shape[:2]
    ch, cw = h // rows, w // cols
    seen = set()
    for f in findings:
        cell = tuple(f["cell"])
        if cell in seen:
            continue
        seen.add(cell)
        r, c = cell
        x1, y1 = int(c * cw), int(r * ch)
        x2, y2 = int(x1 + cw), int(y1 + ch)
        col = (0, 0, 255) if f["level"] == "높음" else \
              (0, 140, 255) if f["level"] == "보통" else (170, 170, 170)
        overlay = img.copy()
        cv2.rectangle(overlay, (x1, y1), (x2, y2), col, -1)
        cv2.addWeighted(overlay, 0.25, img, 0.75, 0, dst=img)  # 반투명 채움
        cv2.rectangle(img, (x1, y1), (x2, y2), col, 4)          # 굵은 테두리
    cv2.imwrite(out_path, img)
