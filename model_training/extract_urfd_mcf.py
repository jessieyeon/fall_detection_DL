"""URFD + MCF -> per-frame 4-feature extraction (same as Le2i extract_features.py).
Resumable: run repeatedly until 'ALL DONE'. Time-boxed to fit sandbox call limits."""
import os, sys, csv, glob, math, time
import cv2
sys.path.insert(0, ".")
sys.path.insert(0, "/tmp")
import mediapipe as mp
from mcf_labels import fall_intervals_for_cam

DATA = "~/Documents/Claude/Projects/FallDetection/data"
OUT_CSV = "features_ext.csv"
PROGRESS = "ext.progress"
TIME_BUDGET = 36.0
PRE_FALL_S, BUF_S = 1.0, 1.0
MCF_BUF_S = 2.0            # larger guard band: absorbs residual camera sync error
SMOOTH = 3
MCF_CAMS = (1, 3, 5, 7)
MCF_FPS = 30.0             # container header lies (120); true capture ~30fps
URFD_FPS = 30.0
L_SH, R_SH, L_HP, R_HP = 11, 12, 23, 24

t_start = time.time()
pose = mp.solutions.pose.Pose(static_image_mode=False, min_detection_confidence=0.5,
                              model_complexity=1)

def feats_stream():
    state = {"vel": [], "tilt": [], "prev": None}
    def reset():
        state["vel"].clear(); state["tilt"].clear(); state["prev"] = None
    def step(frame_bgr, fps, w, h):
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        res = pose.process(rgb)
        if not res.pose_landmarks:
            reset(); return None
        lm = res.pose_landmarks.landmark
        sx = (lm[L_SH].x + lm[R_SH].x) / 2 * w; sy = (lm[L_SH].y + lm[R_SH].y) / 2 * h
        hx = (lm[L_HP].x + lm[R_HP].x) / 2 * w; hy = (lm[L_HP].y + lm[R_HP].y) / 2 * h
        cx, cy = (sx + hx) / 2, (sy + hy) / 2
        tilt = math.degrees(math.atan2(abs(hx - sx), abs(hy - sy) + 1e-6))
        vy = vx = tv = 0.0
        if state["prev"] is not None:
            vy = (cy - state["prev"][1]) / h * fps
            vx = (cx - state["prev"][0]) / w * fps
            state["vel"].append((vy, vx))
            if len(state["vel"]) > SMOOTH: state["vel"].pop(0)
            vy = sum(v[0] for v in state["vel"]) / len(state["vel"])
            vx = sum(v[1] for v in state["vel"]) / len(state["vel"])
        if state["tilt"]:
            tv = (tilt - state["tilt"][-1]) * fps
        state["tilt"].append(tilt)
        if len(state["tilt"]) > SMOOTH: state["tilt"].pop(0)
        state["prev"] = (cx, cy)
        return vy, vx, tilt, tv
    return step, reset

def label_for(frame, intervals, fps, buf_s):
    """1 = pre-fall window, 0 = clearly normal, None = drop (fall/guard band)."""
    pre = int(round(PRE_FALL_S * fps)); buf = int(round(buf_s * fps))
    lab = 0
    for (s, e) in intervals:
        if s - pre <= frame < s:
            return 1
        if s - pre - buf <= frame <= e + buf:
            lab = None
    return lab

def imread_retry(p, tries=2):
    for i in range(tries):
        img = cv2.imread(p)
        if img is not None: return img
        time.sleep(0.1)
    return None

# ---------- task list ----------
def urfd_onset(csv_path):
    onset = end = None
    with open(csv_path) as f:
        for row in csv.reader(f):
            if len(row) < 3: continue
            fr, lab = int(row[1]), int(row[2])
            if lab >= 0:
                if onset is None: onset = fr
                if lab == 0: end = fr
    if onset is not None and end is None: end = onset
    return onset, end

tasks = []
fall_onsets = {}
for line in open(os.path.join(DATA, "urfd/urfall-cam0-falls.csv")):
    pass
# parse once
import collections
rows = collections.defaultdict(list)
with open(os.path.join(DATA, "urfd/urfall-cam0-falls.csv")) as f:
    for row in csv.reader(f):
        if len(row) >= 3: rows[row[0]].append((int(row[1]), int(row[2])))
for seq, rr in rows.items():
    on = next((fr for fr, l in rr if l >= 0), None)
    en = max((fr for fr, l in rr if l == 0), default=on)
    fall_onsets[seq] = (on, en)

for d in sorted(glob.glob(os.path.join(DATA, "urfd", "fall-*-cam0-rgb"))):
    seq = os.path.basename(d)[:7]  # fall-XX
    tasks.append(("urfd", d, seq, fall_onsets.get(seq, (None, None))))
for d in sorted(glob.glob(os.path.join(DATA, "urfd", "adl-*-cam0-rgb"))):
    tasks.append(("urfd", d, os.path.basename(d)[:6], (None, None)))
for sc in range(1, 23):
    hits = glob.glob(os.path.join(DATA, "mcf", f"chute{sc:02d}*"))
    if not hits: continue
    for cam in MCF_CAMS:
        av = os.path.join(sorted(hits)[0], f"cam{cam}.avi")
        if os.path.isfile(av):
            tasks.append(("mcf", av, f"chute{sc:02d}/cam{cam}", (sc, cam)))

done = set()
if os.path.isfile(PROGRESS):
    done = set(l.strip() for l in open(PROGRESS) if l.strip())

fieldnames = ["folder", "video", "frame", "vertical_velocity", "horizontal_velocity",
              "tilt_angle_deg", "tilt_angular_velocity", "label"]
new_file = not os.path.isfile(OUT_CSV)
out = open(OUT_CSV, "a", newline="")
w = csv.DictWriter(out, fieldnames=fieldnames)
if new_file: w.writeheader()
prog = open(PROGRESS, "a")

step, reset = feats_stream()
n_done = 0
tasks.sort(key=lambda t: 0 if t[0]=="mcf" else 1)
for kind, path, name, meta in tasks:
    key = f"{kind}/{name}"
    if key in done: continue
    if time.time() - t_start > TIME_BUDGET:
        print(f"TIME UP ({n_done} new done this run)"); sys.exit(0)
    reset()
    wrote = 0
    try:
        if kind == "urfd":
            onset, end = meta
            intervals = [(onset, end)] if onset else []
            pngs = sorted(glob.glob(os.path.join(path, "*.png")))
            unreadable = 0
            def _probe(p):
                try:
                    with open(p,'rb') as fh: return len(fh.read(64))==64
                except OSError: return False
            probes=[pngs[0], pngs[len(pngs)//3], pngs[2*len(pngs)//3], pngs[-1]]
            if not all(_probe(p) for p in probes):
                print(f"{key}: unreadable -> later", flush=True); continue
            consec=0
            for i, p in enumerate(pngs, 1):
                img = imread_retry(p)
                if img is None:
                    unreadable += 1; consec += 1; reset()
                    if consec > 15:
                        unreadable = len(pngs); break
                    continue
                consec=0
                r = step(img, URFD_FPS, img.shape[1], img.shape[0])
                if r is None: continue
                lab = label_for(i, intervals, URFD_FPS, BUF_S)
                if lab is None: continue
                w.writerow(dict(folder="URFD", video=name, frame=i,
                                vertical_velocity=r[0], horizontal_velocity=r[1],
                                tilt_angle_deg=r[2], tilt_angular_velocity=r[3], label=lab))
                wrote += 1
            if unreadable > len(pngs) * 0.3:
                print(f"{key}: {unreadable}/{len(pngs)} unreadable -> retry later", flush=True)
                continue  # do NOT mark done
        else:
            sc, cam = meta
            intervals = fall_intervals_for_cam(sc, cam)
            cap = cv2.VideoCapture(path)
            fi = 0
            while True:
                ok, f = cap.read()
                if not ok: break
                fi += 1
                f = cv2.resize(f, (480, 320))
                r = step(f, MCF_FPS, 480, 320)
                if r is None: continue
                lab = label_for(fi, intervals, MCF_FPS, MCF_BUF_S)
                if lab is None: continue
                w.writerow(dict(folder="MCF", video=name.replace("/", "_"), frame=fi,
                                vertical_velocity=r[0], horizontal_velocity=r[1],
                                tilt_angle_deg=r[2], tilt_angular_velocity=r[3], label=lab))
                wrote += 1
            cap.release()
    except OSError as e:
        print(f"{key}: OSError {e} -> retry later", flush=True); continue
    out.flush()
    prog.write(key + "\n"); prog.flush()
    n_done += 1
    print(f"done {key} ({wrote} rows)", flush=True)

print("ALL DONE")
