"""v6 학습 — 카메라 거리 정규화 + 실험 A 에서 고른 시간 창.

v4 대비 바뀌는 것은 두 가지뿐이다.
  1) 파생 특징 4개 추가 (add_normalized) — 카메라 거리 의존을 없앤다
  2) 시간 창을 실험 A 의 결론(3초까지)으로 교체

특징 정의·증강·분할·분류기는 exp_window.py 의 것을 그대로 재사용한다. 같은 분할
(random_state=42)이라 v4·실험A 결과와 숫자를 직접 비교할 수 있다.

실행:
    python3 model_training/train_v6.py [features_v6.csv] [출력디렉터리]
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import exp_window as ew                                          # noqa: E402

# 실험 A 결론: W75(0.2/0.5/1.0/2.0/3.0초). docs/모델-v6-실험.md 참고.
WINDOWS = (5, 12, 25, 50, 75)

# v4 의 7개 + v6 파생 4개. 원시 길이(torso_n 등)는 특징으로 쓰지 않는다 —
# 그것은 카메라 거리 정보 그 자체라, 넣으면 모델이 '이 카메라'를 외워버린다.
BASE_V6 = ew.BASE + ["vy_torso", "vx_torso", "hip_h", "torso_ratio"]
ROLL_V6 = BASE_V6 + ["speed_mag"]
SLOPE_COLS_V6 = ew.SLOPE_COLS + ("hip_h", "vy_torso")

RAW_LENGTHS = ["torso_n", "body_n", "hip_y", "ankle_y"]

# add_normalized 의 0 나눗셈 방지 하한. temporal_risk.derive_v6 도 같은 값을 써야 한다.
MIN_TORSO, MIN_BODY = 0.02, 0.05


def add_normalized(df):
    """카메라 거리에 불변인 파생 특징 4개.

    torso_n(어깨→엉덩이 거리 / 화면높이)은 '이 카메라에서 이 사람이 얼마나 크게
    보이는가'다. 속도를 이걸로 나누면 단위가 '몸통길이/초'가 되어, 카메라가 멀어져도
    같은 낙상은 같은 값이 된다.

    hip_h 는 발목 기준 엉덩이 높이를 키(body_n)로 나눈 값이다. 서 있으면 ~0.5,
    앉으면 ~0.25, 누우면 ~0 이라 '앉기 vs 낙상'을 가르는 데 직접 쓰인다.
    바닥 위치를 카메라마다 따로 잴 필요가 없다 — 발목이 곧 바닥이다.

    clip 하한: 사람이 화면 구석에 아주 작게 잡히거나 랜드마크가 겹친 프레임에서
    0 으로 나누는 것을 막는다. 그런 프레임은 어차피 판정에 쓸 수 없다.
    """
    t = df["torso_n"].clip(lower=MIN_TORSO)
    b = df["body_n"].clip(lower=MIN_BODY)
    df["vy_torso"] = df["vertical_velocity"] / t
    df["vx_torso"] = df["horizontal_velocity"] / t
    df["hip_h"] = (df["ankle_y"] - df["hip_y"]) / b
    df["torso_ratio"] = t / b
    return df


def add_temporal_v6(df):
    """exp_window.add_temporal 과 같은 구조. 롤링 대상만 v6 특징으로 넓힌다.

    속도 관련 파생(speed_mag, vert_accel)은 **정규화 속도**를 쓴다. 원시 속도로
    만들면 그 값만 카메라 거리에 다시 끌려가서 정규화한 의미가 반감된다.
    """
    out = []
    for _, g in df.groupby("video_id", sort=False):
        g = g.sort_values("frame").copy()
        g["speed_mag"] = np.hypot(g["vy_torso"], g["vx_torso"])
        g["vert_accel"] = g["vy_torso"].diff().fillna(0) * ew.FPS_T
        g["tilt_accel"] = g["tilt_angular_velocity"].diff().fillna(0) * ew.FPS_T
        g["tilt3d_vel"] = g["tilt3d_deg"].diff().fillna(0) * ew.FPS_T
        g["aspect_vel"] = g["aspect_ratio"].diff().fillna(0) * ew.FPS_T
        g["shoulder_vel"] = g["shoulder_y"].diff().fillna(0) * ew.FPS_T
        g["hip_h_vel"] = g["hip_h"].diff().fillna(0) * ew.FPS_T
        for w in WINDOWS:
            for c in ROLL_V6:
                r = g[c].rolling(w, min_periods=1)
                g[f"{c}_m{w}"] = r.mean()
                g[f"{c}_s{w}"] = r.std().fillna(0)
                g[f"{c}_r{w}"] = r.max() - r.min()
        for c in SLOPE_COLS_V6:
            g[f"{c}_slope"] = (g[c] - g[c].shift(ew.SLOPE_LAG)).fillna(0) \
                / (ew.SLOPE_LAG / ew.FPS_T)
        for c in BASE_V6:
            g[f"{c}_ewma"] = g[c].ewm(alpha=ew.EWMA_ALPHA).mean()
        out.append(g)
    return pd.concat(out)


def augment_video(g, kind):
    """exp_window.augment_video 의 v6 판. 미러링 때 정규화 속도도 함께 뒤집는다."""
    g = g.sort_values("frame").reset_index(drop=True)
    if kind == "mirror":
        a = g.copy()
        a["horizontal_velocity"] = -a["horizontal_velocity"]
        a["vx_torso"] = -a["vx_torso"]
    else:
        s = float(kind)
        n = max(int(len(g) / s), 15)
        pos = np.linspace(0, len(g) - 1, n)
        a = pd.DataFrame({c: np.interp(pos, np.arange(len(g)), g[c].values)
                          for c in BASE_V6})
        # 속도류는 재생속도에 비례해 커진다. 길이·비율류(hip_h, torso_ratio)는 그대로.
        for c in ("vertical_velocity", "horizontal_velocity",
                  "tilt_angular_velocity", "vy_torso", "vx_torso"):
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
        for s in ew.SPEED_FACTORS:
            parts.append(augment_video(g, s))
    return pd.concat(parts, ignore_index=True)


def score(clf, feats, te):
    t = add_temporal_v6(te.copy()).copy()
    t["proba"] = clf.predict_proba(t[feats])[:, 1]
    t["proba_sm"] = ew.smooth_proba(t)
    return t


def main():
    csv_path = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
        "~/Documents/Claude/Projects/FallDetection/data/features_v6.csv")
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "/tmp/daon_exp"
    os.makedirs(out_dir, exist_ok=True)
    t0 = time.time()

    d = pd.read_csv(csv_path)
    d["video_id"] = d["dataset"] + "/" + d["video"]
    d = add_normalized(d)
    print(f"불러옴: {len(d)} 프레임, {d['video_id'].nunique()} 영상", flush=True)

    le2i_tr, le2i_te, urfd_tr, urfd_te, own, mcf_te = ew.split_data(d)

    scored, clf, feats = {}, None, None
    for test_p in ("p1", "p2"):
        own_tr = own[own.person != test_p].drop(columns=["person"])
        own_te = own[own.person == test_p].drop(columns=["person"])
        own3 = pd.concat([own_tr.assign(video_id=own_tr.video_id + f"~{k}")
                          for k in range(3)])
        raw = build_augmented(pd.concat([le2i_tr, urfd_tr, own3], ignore_index=True))
        f = add_temporal_v6(raw)
        feats = [c for c in f.columns
                 if c not in ("dataset", "video", "frame", "label", "video_id",
                              "person", "scen") and c not in RAW_LENGTHS]
        clf = HistGradientBoostingClassifier(max_iter=400, max_depth=6,
                                             learning_rate=0.08,
                                             class_weight="balanced", random_state=42)
        clf.fit(f[feats], f["label"])
        scored[f"own_{test_p}"] = (score(clf, feats, own_te), 30.0, 0.5)
        print(f"  {test_p} 학습 완료 ({len(feats)} feats, {time.time()-t0:.0f}s)", flush=True)
        if test_p == "p2":
            # 공개 홀드아웃은 v4·실험A 와 같이 p2 폴드 모델로 평가
            scored["Le2i"] = (score(clf, feats, le2i_te), 25.0, 0.0)
            scored["URFD"] = (score(clf, feats, urfd_te), 30.0, 0.0)
            scored["MCF"] = (score(clf, feats, mcf_te.drop(columns=["scen"])), 30.0, 0.0)

    sweep = []
    for thr, pers in itertools.product((0.05, 0.1, 0.15, 0.3, 0.5), (1, 2, 3, 5)):
        row = {"thr": thr, "pers": pers}
        for key, (t, fps, grace) in scored.items():
            row[key] = ew.evaluate(t, thr, pers, fps, grace)
        a, b = row["own_p1"], row["own_p2"]
        row["own"] = {"catch": a["catch"] + b["catch"], "nfall": a["nfall"] + b["nfall"],
                      "fp": round((a["fp"] * a["nadl"] + b["fp"] * b["nadl"])
                                  / max(a["nadl"] + b["nadl"], 1), 2),
                      "lead": a["lead"] if a["lead"] is not None else b["lead"]}
        sweep.append(row)

    best = min(sweep, key=lambda r: (-r["own"]["catch"], r["own"]["fp"]))
    with open(os.path.join(out_dir, "v6_sweep.json"), "w") as fh:
        json.dump({"windows": list(WINDOWS), "n_features": len(feats), "sweep": sweep},
                  fh, ensure_ascii=False, indent=1)

    bundle = {"model": clf, "features": feats, "base_features": BASE_V6,
              "windows": list(WINDOWS), "slope_cols": list(SLOPE_COLS_V6),
              "slope_lag": ew.SLOPE_LAG, "fps": ew.FPS_T,
              "ewma_alpha": ew.EWMA_ALPHA, "proba_ewma_alpha": ew.PROBA_EWMA_ALPHA,
              "prob_threshold": best["thr"], "persistence": best["pers"],
              "version": 6}
    # joblib 은 여기서만 임포트한다 — add_normalized 만 쓰는 테스트가 joblib 없이 돈다.
    import joblib
    joblib.dump(bundle, "fall_risk_model_v6.joblib")

    o, l, u, m = best["own"], best["Le2i"], best["URFD"], best["MCF"]
    print(f"\n최적 동작점: thr {best['thr']} / pers {best['pers']}")
    print(f"  자체 클립 {o['catch']}/{o['nfall']} @FP {o['fp']} (선행 {o['lead']}초)")
    print(f"  Le2i {l['catch']}/{l['nfall']} @FP {l['fp']}")
    print(f"  URFD {u['catch']}/{u['nfall']} @FP {u['fp']}")
    print(f"  MCF  {m['catch']}/{m['nfall']}")
    print(f"fall_risk_model_v6.joblib 저장됨 ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
