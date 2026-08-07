"""v6 특징 재추출 — 카메라 거리·화각에 불변인 정규화를 위한 원시 길이 4개 추가.

배경(지도교수 피드백):
  "픽셀/프레임 단위 속도는 카메라 거리와 fps에 따라 값 자체가 달라진다. 어깨-엉덩이
   거리로 나누고 초 단위로 환산하는 등 정규화가 필요하다. 절대 높이를 추가하면
   앉기와 낙상을 더 잘 가를 수 있다 — 엉덩이 중심 높이를 서 있을 때 키로 정규화."

v4 CSV 에는 정규화에 필요한 '길이'가 하나도 없다. 속도는 이미 화면 높이로 나누고
초 단위로 환산했지만(그래서 fps 는 이미 무관), **화면 높이는 카메라가 얼마나 멀리
있느냐에 따라 사람의 크기가 달라지므로 거리 불변이 아니다.** 사람이 화면에서 2배
크게 잡히면 같은 낙상이 2배 빠른 속도로 기록된다.

그래서 다음 4개를 추가로 저장한다. 전부 **화면 높이 기준 정규화 길이**라서
해상도에는 무관하고, 카메라 거리 정보만 담고 있다 (그걸로 나눠서 없앨 것이다).

  torso_n   어깨중점→엉덩이중점 거리 / 화면높이   ← 속도 정규화의 기준자
  body_n    인체 바운딩박스 높이 / 화면높이       ← '서 있을 때 키'의 대용
  hip_y     엉덩이 중점 y (0=위, 1=아래)          ← 절대 높이
  ankle_y   양 발목 y 평균                        ← 바닥 기준선(카메라별 바닥 위치 불필요)

파생 특징(정규화·비율)은 학습 쪽(train_v6.py)에서 만든다. 원시 길이를 그대로
남겨두어야 나중에 다른 정규화를 시도할 때 재추출을 반복하지 않는다.

나머지(포즈 모델 설정, 라벨 규칙, 데이터셋 목록)는 extract_features_v4.py 와
완전히 동일하다 — 그래야 v4 대비 차이를 '특징 추가' 하나로 귀속시킬 수 있다.

실행 (맥에서, 재개 가능):
    python3 model_training/extract_v6.py <data 경로> [출력 csv]
  중단해도 다시 실행하면 이어서 한다(진행 파일 .v6.progress).
  327개 영상 기준 맥북 CPU 로 30~60분 정도 걸린다.
"""
import collections
import csv
import glob
import math
import os
import sys
import time

import cv2
import mediapipe as mp

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcf_labels import fall_intervals_for_cam           # noqa: E402

# 자체 촬영 클립의 낙상 시작 시각(초). extract_features_v4.py 와 동일.
ONSETS = {"fall_p1_forward_01": 4.38, "fall_p1_forward_02": 0.51,
          "fall_p1_backward_01": 3.64, "fall_p1_backward_02": 2.84,
          "fall_p1_side_01": 0.52, "fall_p1_side_02": 0.96,
          "fall_p1_chair_01": 0.44, "fall_p2_forward_01": 2.94,
          "fall_p2_forward_02": 0.59, "fall_p2_backward_01": 1.24,
          "fall_p2_backward_02": 2.96, "fall_p2_side_01": 3.55,
          "fall_p2_forward_03": 1.08, "fall_p2_chair_01": 1.64,
          "fall_p2_side_02": 1.00, "fall_p2_side_03": 2.75,
          "fall_p2_backward_03": 1.69}

PRE_S, BUF_S, MCF_BUF_S, FALL_DUR_S = 1.0, 1.0, 2.0, 1.5
SMOOTH = 3
MCF_CAMS = (1, 3, 5, 7)
L_SH, R_SH, L_HP, R_HP = 11, 12, 23, 24
L_AN, R_AN = 27, 28

COLS = ["dataset", "video", "frame",
        "vertical_velocity", "horizontal_velocity", "tilt_angle_deg",
        "tilt_angular_velocity", "tilt3d_deg", "aspect_ratio", "shoulder_y",
        # --- v6 신규 ---
        "torso_n", "body_n", "hip_y", "ankle_y",
        "label"]

pose = mp.solutions.pose.Pose(static_image_mode=False,
                              min_detection_confidence=0.5, model_complexity=1)


class FS:
    """프레임 하나에서 특징을 뽑는 상태 기계. v4 와 같은 스무딩(3프레임)."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.vel = []
        self.tilt = []
        self.prev = None

    def step(self, frame, fps):
        h, w = frame.shape[:2]
        res = pose.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        if not res.pose_landmarks:
            self.reset()
            return None
        lm = res.pose_landmarks.landmark

        sx = (lm[L_SH].x + lm[R_SH].x) / 2 * w
        sy = (lm[L_SH].y + lm[R_SH].y) / 2 * h
        hx = (lm[L_HP].x + lm[R_HP].x) / 2 * w
        hy = (lm[L_HP].y + lm[R_HP].y) / 2 * h
        cx, cy = (sx + hx) / 2, (sy + hy) / 2
        tilt = math.degrees(math.atan2(abs(hx - sx), abs(hy - sy) + 1e-6))

        xs = [p.x for p in lm]
        ys = [p.y for p in lm]
        aspect = ((max(xs) - min(xs)) * w) / (((max(ys) - min(ys)) * h) + 1e-6)
        sh_y = (lm[L_SH].y + lm[R_SH].y) / 2

        # --- v6 신규: 화면높이로 정규화한 길이들 ---
        # torso_n 은 '이 카메라에서 이 사람이 얼마나 크게 보이는가'의 척도다.
        # 속도를 이 값으로 나누면 '몸통길이/초'가 되어 카메라 거리에 불변이 된다.
        torso_n = math.hypot((hx - sx) / w, (hy - sy) / h)
        body_n = max(ys) - min(ys)
        hip_y = (lm[L_HP].y + lm[R_HP].y) / 2
        ankle_y = (lm[L_AN].y + lm[R_AN].y) / 2

        t3 = tilt
        if res.pose_world_landmarks:
            wl = res.pose_world_landmarks.landmark
            dx = (wl[L_HP].x + wl[R_HP].x) / 2 - (wl[L_SH].x + wl[R_SH].x) / 2
            dy = (wl[L_HP].y + wl[R_HP].y) / 2 - (wl[L_SH].y + wl[R_SH].y) / 2
            dz = (wl[L_HP].z + wl[R_HP].z) / 2 - (wl[L_SH].z + wl[R_SH].z) / 2
            t3 = math.degrees(math.atan2(math.hypot(dx, dz), abs(dy) + 1e-9))

        vy = vx = tv = 0.0
        if self.prev is not None:
            vy = (cy - self.prev[1]) / h * fps
            vx = (cx - self.prev[0]) / w * fps
            self.vel.append((vy, vx))
            if len(self.vel) > SMOOTH:
                self.vel.pop(0)
            vy = sum(v[0] for v in self.vel) / len(self.vel)
            vx = sum(v[1] for v in self.vel) / len(self.vel)
        if self.tilt:
            tv = (tilt - self.tilt[-1]) * fps
        self.tilt.append(tilt)
        if len(self.tilt) > SMOOTH:
            self.tilt.pop(0)
        self.prev = (cx, cy)
        return (vy, vx, tilt, tv, t3, aspect, sh_y,
                torso_n, body_n, hip_y, ankle_y)


def lab_for(fi, intervals, fps, buf_s):
    """낙상 '직전 1초'만 양성. 낙상 중/직후는 None(=학습에서 제외)."""
    pre = int(round(PRE_S * fps))
    buf = int(round(buf_s * fps))
    lab = 0
    for s, e in intervals:
        if s - pre <= fi < s:
            return 1
        if s - pre - buf <= fi <= e + buf:
            lab = None
    return lab


def le2i_ann(base, vname):
    for nm in ("Annotation_files", "Annotations_files"):
        p = os.path.join(base, nm, os.path.splitext(vname)[0] + ".txt")
        if os.path.isfile(p):
            ls = [l.strip() for l in open(p) if l.strip()]
            try:
                return int(ls[0]), int(ls[1])
            except (ValueError, IndexError):
                return 0, 0
    return None


def build_tasks(data):
    tasks = []
    for fold in ("Home_01", "Home_02", "Coffee_room_01", "Coffee_room_02"):
        base = os.path.join(data, "le2i", fold, fold)
        for vp in sorted(glob.glob(os.path.join(base, "Videos", "*.avi"))):
            tasks.append(("le2i", vp, f"{fold}/{os.path.basename(vp)}", (base,)))

    rows = collections.defaultdict(list)
    urfd_csv = os.path.join(data, "urfd/urfall-cam0-falls.csv")
    if os.path.isfile(urfd_csv):
        with open(urfd_csv) as f:
            for row in csv.reader(f):
                if len(row) >= 3:
                    rows[row[0]].append((int(row[1]), int(row[2])))
    u_on = {}
    for sq, rr in rows.items():
        on = next((fr for fr, l in rr if l >= 0), None)
        u_on[sq] = (on, max((fr for fr, l in rr if l == 0), default=on))
    for d in sorted(glob.glob(os.path.join(data, "urfd", "*-cam0-rgb"))):
        st = os.path.basename(d).split("-cam0")[0]
        tasks.append(("urfd", d, st, u_on.get(st, (None, None))))

    for sc in range(1, 23):
        hits = sorted(glob.glob(os.path.join(data, "mcf", f"chute{sc:02d}*")))
        if hits:
            for cam in MCF_CAMS:
                av = os.path.join(hits[0], f"cam{cam}.avi")
                if os.path.isfile(av):
                    tasks.append(("mcf", av, f"chute{sc:02d}_cam{cam}", (sc, cam)))

    for p in sorted(glob.glob(data + "/raw/*.mov") + glob.glob(data + "/raw/*.MOV")):
        tasks.append(("own", p, os.path.splitext(os.path.basename(p))[0], ()))
    return tasks


def main():
    data = sys.argv[1] if len(sys.argv) > 1 else "data"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "data/features_v6.csv"
    prog_path = out_path + ".progress"
    budget = float(os.environ.get("V6_BUDGET_S", "0"))     # 0 = 무제한
    t0 = time.time()

    tasks = build_tasks(data)
    done = set(l.strip() for l in open(prog_path)) if os.path.isfile(prog_path) else set()
    is_new = not os.path.isfile(out_path)
    out = open(out_path, "a", newline="")
    w = csv.writer(out)
    if is_new:
        w.writerow(COLS)
    prog = open(prog_path, "a")
    fs = FS()

    print(f"영상 {len(tasks)}개 중 {len(tasks)-len(done)}개 남음", flush=True)
    for kind, path, name, meta in tasks:
        key = f"{kind}/{name}"
        if key in done:
            continue
        if budget and time.time() - t0 > budget:
            print("시간 예산 소진 — 다시 실행하면 이어서 합니다")
            break
        fs.reset()
        n = 0
        try:
            if kind == "urfd":
                on, en = meta
                iv = [(on, en)] if on else []
                fps = 30.0
                for i, p in enumerate(sorted(glob.glob(os.path.join(path, "*.png"))), 1):
                    img = cv2.imread(p)
                    if img is None:
                        fs.reset()
                        continue
                    r = fs.step(img, fps)
                    if r is None:
                        continue
                    lab = lab_for(i, iv, fps, BUF_S)
                    if lab is not None:
                        w.writerow(["URFD", name, i] + [round(x, 5) for x in r] + [lab])
                        n += 1
            else:
                cap = cv2.VideoCapture(path)
                if kind == "le2i":
                    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
                    ann = le2i_ann(meta[0], os.path.basename(path))
                    iv = [] if (ann is None or ann[0] == 0) else [ann]
                    buf, resize = BUF_S, None
                elif kind == "mcf":
                    fps = 30.0
                    iv = fall_intervals_for_cam(*meta)
                    buf, resize = MCF_BUF_S, (480, 320)
                else:
                    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
                    on = int(round(ONSETS[name] * fps)) if name in ONSETS else None
                    iv = [(on, on + int(FALL_DUR_S * fps))] if on else []
                    buf, resize = BUF_S, "half"
                fi = 0
                while True:
                    ok, f = cap.read()
                    if not ok:
                        break
                    fi += 1
                    if resize == "half":
                        h0, w0 = f.shape[:2]
                        sc = 480 / max(h0, w0)
                        f = cv2.resize(f, (int(w0 * sc), int(h0 * sc)))
                    elif resize:
                        f = cv2.resize(f, resize)
                    r = fs.step(f, fps)
                    if r is None:
                        continue
                    lab = lab_for(fi, iv, fps, buf)
                    if lab is not None:
                        vid = name.replace("/", "_") if kind == "mcf" else name
                        w.writerow([kind.upper(), vid, fi] + [round(x, 5) for x in r] + [lab])
                        n += 1
                cap.release()
        except (OSError, cv2.error) as exc:
            print(f"{key} 실패 -> 나중에 재시도 ({exc})", flush=True)
            continue
        out.flush()
        prog.write(key + "\n")
        prog.flush()
        print(f"done {key} {n}프레임 ({time.time()-t0:.0f}s)", flush=True)
    print("완료")


if __name__ == "__main__":
    main()
