"""실험 A — 시간 윈도우 길이가 성능에 미치는 영향.

배경(지도교수 피드백): "낙상은 0.5~1초짜리 궤적인데 프레임을 개별 분류하고
'3프레임 연속'으로 처리하면 행동 정보를 인코딩하기 어렵다. 윈도우 안에 들어가는
프레임을 늘려라."

v4 배포 모델의 윈도우는 (5, 12, 25) 프레임 = 25fps 기준 0.2 / 0.48 / 1.0초다.
가장 긴 창이 정확히 낙상 지속시간과 같아서, '낙상 직전 1초'와 '낙상 자체'를
구분할 여유가 없다. 여기서는 창을 2초·3초까지 늘려 같은 벤치마크로 비교한다.

바꾸는 것은 WINDOWS 하나뿐이다. 특징 정의·증강·분할·분류기·동작점은 v4와
동일하게 두어야 차이가 창 길이 때문임을 말할 수 있다.

주의: persistence(3프레임 연속)는 여기서 건드리지 않는다. 그것은 '판정 후
지속 요건'이고 창 길이는 '한 프레임이 보는 과거의 길이'라 서로 다른 손잡이다.
창을 늘리면 한 프레임이 이미 긴 궤적을 보게 되므로 persistence 의존도가 낮아진다
— 그 효과는 아래 동작점 스윕에서 pers=1~5 로 함께 확인한다.

실행:
    python3 model_training/exp_window.py <features_v4.csv 경로> [출력디렉터리]
"""
import itertools
import json
import os
import sys
import time
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import GroupShuffleSplit

BASE = ["vertical_velocity", "horizontal_velocity", "tilt_angle_deg",
        "tilt_angular_velocity", "tilt3d_deg", "aspect_ratio", "shoulder_y"]
ROLL = BASE + ["speed_mag"]
FPS_T = 25.0
SLOPE_LAG = 12
EWMA_ALPHA = 0.3
PROBA_EWMA_ALPHA = 0.4
SPEED_FACTORS = (0.85, 1.15)
SLOPE_COLS = ("tilt_angle_deg", "vertical_velocity", "tilt3d_deg",
              "aspect_ratio", "shoulder_y")

# 비교할 창 구성. 초 단위(25fps 기준)를 주석에 적어 둔다.
CONFIGS = {
    "W25_base": (5, 12, 25),           # 0.2 / 0.5 / 1.0초  ← v4 배포값
    "W50": (5, 12, 25, 50),            # + 2.0초
    "W75": (5, 12, 25, 50, 75),        # + 3.0초
    "W50_only_long": (12, 25, 50),     # 짧은 창을 빼면 손해인지 확인
}


def add_temporal(df, windows):
    out = []
    for _, g in df.groupby("video_id", sort=False):
        g = g.sort_values("frame").copy()
        g["speed_mag"] = np.hypot(g["vertical_velocity"], g["horizontal_velocity"])
        g["vert_accel"] = g["vertical_velocity"].diff().fillna(0) * FPS_T
        g["tilt_accel"] = g["tilt_angular_velocity"].diff().fillna(0) * FPS_T
        g["tilt3d_vel"] = g["tilt3d_deg"].diff().fillna(0) * FPS_T
        g["aspect_vel"] = g["aspect_ratio"].diff().fillna(0) * FPS_T
        g["shoulder_vel"] = g["shoulder_y"].diff().fillna(0) * FPS_T
        for w in windows:
            for c in ROLL:
                r = g[c].rolling(w, min_periods=1)
                g[f"{c}_m{w}"] = r.mean()
                g[f"{c}_s{w}"] = r.std().fillna(0)
                g[f"{c}_r{w}"] = r.max() - r.min()
        for c in SLOPE_COLS:
            g[f"{c}_slope"] = (g[c] - g[c].shift(SLOPE_LAG)).fillna(0) / (SLOPE_LAG / FPS_T)
        for c in BASE:
            g[f"{c}_ewma"] = g[c].ewm(alpha=EWMA_ALPHA).mean()
        out.append(g)
    return pd.concat(out)


def augment_video(g, kind):
    g = g.sort_values("frame").reset_index(drop=True)
    if kind == "mirror":
        a = g.copy()
        a["horizontal_velocity"] = -a["horizontal_velocity"]
    else:
        s = float(kind)
        n = max(int(len(g) / s), 15)
        pos = np.linspace(0, len(g) - 1, n)
        a = pd.DataFrame({c: np.interp(pos, np.arange(len(g)), g[c].values) for c in BASE})
        for c in ("vertical_velocity", "horizontal_velocity", "tilt_angular_velocity"):
            a[c] *= s
        a["label"] = g["label"].values[np.round(pos).astype(int)]
        a["frame"] = np.arange(1, n + 1)
        a["dataset"] = g["dataset"].iloc[0]
        a["video"] = g["video"].iloc[0]
    a["video_id"] = g["video_id"].iloc[0] + f"#{kind}"
    return a


def build_augmented(tr):
    parts = [tr]
    for _, g in tr.groupby("video_id", sort=False):
        parts.append(augment_video(g, "mirror"))
        for s in SPEED_FACTORS:
            parts.append(augment_video(g, s))
    return pd.concat(parts, ignore_index=True)


def smooth_proba(t):
    sm = []
    for _, g in t.groupby("video_id", sort=False):
        sm.append(g.sort_values("frame")["proba"].ewm(alpha=PROBA_EWMA_ALPHA).mean())
    return pd.concat(sm)


def trigger_frame(frames, preds, pers):
    run = 0
    for fr, p in zip(frames, preds):
        if p == 1:
            run += 1
            if run == pers:
                return fr
        else:
            run = 0
    return None


def count_events(preds, pers):
    ev = run = 0
    fired = False
    for p in preds:
        if p == 1:
            run += 1
            if run == pers and not fired:
                ev += 1
                fired = True
        else:
            run = 0
            fired = False
    return ev


def evaluate(t, thr, pers, fps, grace_s=0.0):
    t = t.copy()
    t["pred"] = (t["proba_sm"] >= thr).astype(int)
    nf = nc = na = nfp = 0
    leads = []
    for _, g in t.sort_values("frame").groupby("video_id"):
        has_fall = (g["label"] == 1).any()
        tf = trigger_frame(g["frame"].tolist(), g["pred"].tolist(), pers)
        if has_fall:
            nf += 1
            onset = g.loc[g["label"] == 1, "frame"].max() + 1
            if tf is not None and tf <= onset + grace_s * fps:
                nc += 1
                leads.append((onset - tf) / fps)
        else:
            na += 1
            nfp += count_events(g["pred"].tolist(), pers)
    return dict(catch=nc, nfall=nf, fp=round(nfp / max(na, 1), 2), nadl=na,
                lead=None if not leads else round(float(np.median(leads)), 2))


def split_data(d):
    """v4 와 동일한 분할(random_state 고정)이라 숫자를 직접 비교할 수 있다."""
    le2i = d[d.dataset == "LE2I"]
    urfd = d[d.dataset == "URFD"]
    own = d[d.dataset == "OWN"].copy()
    own["person"] = own["video"].str.extract(r"_(p\d)_")[0]
    mcf = d[d.dataset == "MCF"].copy()
    mcf["scen"] = mcf["video"].str.split("_").str[0]

    gss = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=42)
    i, j = next(gss.split(le2i, groups=le2i["video_id"]))
    le2i_tr, le2i_te = le2i.iloc[i], le2i.iloc[j]

    useq = sorted(urfd["video"].unique())
    ut = set(np.random.RandomState(42).choice(useq, size=len(useq) // 4, replace=False))
    urfd_tr, urfd_te = urfd[~urfd["video"].isin(ut)], urfd[urfd["video"].isin(ut)]

    scen = sorted(mcf["scen"].unique())
    mt = set(np.random.RandomState(42).choice(scen, size=len(scen) // 4, replace=False))
    mcf_te = mcf[mcf["scen"].isin(mt)]
    keep = mcf_te.groupby("video_id")["label"].max()
    mcf_te = mcf_te[mcf_te["video_id"].isin(keep[keep == 1].index)]
    return le2i_tr, le2i_te, urfd_tr, urfd_te, own, mcf_te


def score(clf, feats, te, windows):
    t = add_temporal(te.copy(), windows).copy()
    t["proba"] = clf.predict_proba(t[feats])[:, 1]
    t["proba_sm"] = smooth_proba(t)
    return t


def run_config(name, windows, data, out_dir):
    le2i_tr, le2i_te, urfd_tr, urfd_te, own, mcf_te = data
    t0 = time.time()
    result = {"name": name, "windows": list(windows)}

    scored = {}
    for test_p in ("p1", "p2"):
        own_tr = own[own.person != test_p].drop(columns=["person"])
        own_te = own[own.person == test_p].drop(columns=["person"])
        own3 = pd.concat([own_tr.assign(video_id=own_tr.video_id + f"~{k}") for k in range(3)])
        raw = build_augmented(pd.concat([le2i_tr, urfd_tr, own3], ignore_index=True))
        f = add_temporal(raw, windows)
        feats = [c for c in f.columns
                 if c not in ("dataset", "video", "frame", "label", "video_id", "person", "scen")]
        clf = HistGradientBoostingClassifier(max_iter=400, max_depth=6, learning_rate=0.08,
                                             class_weight="balanced", random_state=42)
        clf.fit(f[feats], f["label"])
        result["n_features"] = len(feats)
        scored[f"own_{test_p}"] = (score(clf, feats, own_te, windows), 30.0, 0.5)
        print(f"  [{name}] {test_p} 학습 완료 ({len(feats)} feats, {time.time()-t0:.0f}s)",
              flush=True)
        if test_p == "p2":
            # 공개 홀드아웃은 v4 와 같이 p2 폴드 모델(=p1 포함 학습)로 평가
            scored["Le2i"] = (score(clf, feats, le2i_te, windows), 25.0, 0.0)
            scored["URFD"] = (score(clf, feats, urfd_te, windows), 30.0, 0.0)
            scored["MCF"] = (score(clf, feats, mcf_te.drop(columns=["scen"]), windows), 30.0, 0.0)

    # 동작점 스윕: 창을 늘리면 최적 임계값이 이동하므로 v4 기본값만 보면 불공정하다.
    sweep = []
    for thr, pers in itertools.product((0.05, 0.1, 0.15, 0.3, 0.5), (1, 2, 3, 5)):
        row = {"thr": thr, "pers": pers}
        for key, (t, fps, grace) in scored.items():
            row[key] = evaluate(t, thr, pers, fps, grace)
        # 자체 클립 두 사람을 합산해 하나의 수치로 본다
        a, b = row["own_p1"], row["own_p2"]
        row["own"] = {"catch": a["catch"] + b["catch"], "nfall": a["nfall"] + b["nfall"],
                      "fp": round((a["fp"] * a["nadl"] + b["fp"] * b["nadl"])
                                  / max(a["nadl"] + b["nadl"], 1), 2),
                      "lead": a["lead"] if a["lead"] is not None else b["lead"]}
        sweep.append(row)
    result["sweep"] = sweep
    result["seconds"] = round(time.time() - t0, 1)

    with open(os.path.join(out_dir, f"exp_window_{name}.json"), "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(f"  [{name}] 완료 {result['seconds']}s", flush=True)
    return result


def summarize(results):
    """각 구성에서 '자체 클립 감지율을 최대로 하면서 오경보가 가장 낮은' 동작점."""
    lines = ["| 구성 | 창(초) | 특징수 | 동작점 | 자체40클립 | Le2i | URFD | MCF |",
             "|---|---|---|---|---|---|---|---|"]
    for r in results:
        best = None
        for row in r["sweep"]:
            o = row["own"]
            key = (-o["catch"], o["fp"])
            if best is None or key < best[0]:
                best = (key, row)
        row = best[1]
        o, l, u, m = row["own"], row["Le2i"], row["URFD"], row["MCF"]
        secs = "/".join(f"{w/FPS_T:.1f}" for w in r["windows"])
        lines.append(
            f"| {r['name']} | {secs} | {r['n_features']} | thr {row['thr']}/pers {row['pers']} "
            f"| {o['catch']}/{o['nfall']} @FP {o['fp']} "
            f"| {l['catch']}/{l['nfall']} @FP {l['fp']} "
            f"| {u['catch']}/{u['nfall']} @FP {u['fp']} "
            f"| {m['catch']}/{m['nfall']} |")
    return "\n".join(lines)


if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/features_v4.csv"
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "/tmp"
    only = sys.argv[3].split(",") if len(sys.argv) > 3 else list(CONFIGS)
    os.makedirs(out_dir, exist_ok=True)

    d = pd.read_csv(csv_path)
    d["video_id"] = d["dataset"] + "/" + d["video"]
    print(f"불러옴: {len(d)} 프레임, {d['video_id'].nunique()} 영상", flush=True)
    data = split_data(d)

    results = []
    for name in only:
        print(f"=== {name} {CONFIGS[name]} ===", flush=True)
        results.append(run_config(name, CONFIGS[name], data, out_dir))

    print("\n" + summarize(results), flush=True)
    with open(os.path.join(out_dir, "exp_window_summary.md"), "w") as f:
        f.write(summarize(results) + "\n")
