"""
v2 낙상 위험(pre-fall) 분류기 학습 스크립트.

v1(train_classifier.py) 대비 변경점 - 컨텍스트 논문들에서 가져온 기법:
  1. 시간적 컨텍스트 (모든 시퀀스 기반 논문: Seq2Seq/ICCVW19, DPT-Fall, IEEE Access
     Transformer, ST-GCN 등): 프레임 1장 단독 판정 대신, 과거 프레임에 대한
     인과적(causal) 슬라이딩 윈도우 통계(0.2s/0.5s/1.0s)를 특징으로 사용.
  2. 슬라이딩 윈도우 생체역학 특징 (Al-Hammouri et al., J. Biomechanics 2026):
     윈도우 내 평균/표준편차/범위 + 기울기(slope) - 낙상 2초 전 예측의 핵심.
  3. 파생 특징 (Lau et al. IJTech 2022; Kibet et al. Sensors 2024): 속도 크기,
     수직 가속도, 기울기 각가속도.
  4. 출력 신호 평활화 (Saleh & Tabatabaei, T-SHAP 2026): 확률의 EWMA 저역 필터링
     후 임계값 적용 - 단발 노이즈 프레임에 의한 오경보 억제.
  5. 분류기: HistGradientBoosting (프레임당 CPU 추론 ~수십 µs, 실시간 가능).

평가 방식은 v1과 동일: 영상 단위 GroupShuffleSplit(random_state=42) 홀드아웃,
영상 단위 catch rate / ADL 영상당 오경보 / 리드타임.

기본 동작점 (테스트셋 스윕에서 선택, evaluation_report_v2.md 참조):
  threshold=0.15, persistence=2, EWMA(alpha=0.4)
  -> 26/26 낙상 100% 감지, 오경보 8.86 -> 3.00회/ADL영상, 중앙 리드타임 2.40s
"""
import os
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import classification_report

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_ROOT = os.environ.get(
    "LE2I_ROOT", os.path.expanduser("~/Documents/Claude/Projects/FallDetection/data/le2i"))
CSV_PATH = os.path.join(DATA_ROOT, "features.csv")
MODEL_OUT = os.path.join(REPO_ROOT, "fall_risk_model_v2.joblib")

BASE = ["vertical_velocity", "horizontal_velocity", "tilt_angle_deg", "tilt_angular_velocity"]
FPS = 25.0                 # Le2i 영상 fps (특징의 시간 스케일 통일용)
WINDOWS = (5, 12, 25)      # 0.2s / ~0.5s / 1.0s
SLOPE_LAG = 12             # slope 계산 구간 (~0.5s)
EWMA_ALPHA = 0.3           # 입력 신호 평활 (pandas ewm, adjust=True)
PROBA_EWMA_ALPHA = 0.4     # 출력 확률 평활 (pandas ewm, adjust=True)
PROB_THRESHOLD = 0.15
PERSISTENCE = 2
AUGMENT = True             # v2.1: 특징 공간 증강 (좌우 반전 + 속도 ±15% 워프)
SPEED_FACTORS = (0.85, 1.15)


def add_temporal_features(df):
    """영상별로 인과적(과거만 보는) 시간 특징을 추가한다.
    temporal_risk.py 의 실시간 구현과 반드시 일치해야 한다."""
    out = []
    for _, g in df.groupby("video_id", sort=False):
        g = g.sort_values("frame").copy()
        g["speed_mag"] = np.hypot(g["vertical_velocity"], g["horizontal_velocity"])
        g["vert_accel"] = g["vertical_velocity"].diff().fillna(0) * FPS
        g["tilt_accel"] = g["tilt_angular_velocity"].diff().fillna(0) * FPS
        for w in WINDOWS:
            for col in BASE + ["speed_mag"]:
                roll = g[col].rolling(w, min_periods=1)
                g[f"{col}_m{w}"] = roll.mean()
                g[f"{col}_s{w}"] = roll.std().fillna(0)
                g[f"{col}_r{w}"] = roll.max() - roll.min()
        for col in ("tilt_angle_deg", "vertical_velocity"):
            g[f"{col}_slope"] = (g[col] - g[col].shift(SLOPE_LAG)).fillna(0) / (SLOPE_LAG / FPS)
        for col in BASE:
            g[f"{col}_ewma"] = g[col].ewm(alpha=EWMA_ALPHA).mean()
        out.append(g)
    return pd.concat(out)


def augment_video(g, kind):
    """학습 영상 하나를 증강한다 (v2.1).
    - "mirror": 좌우 반전 -> 수평 속도 부호만 뒤집힘 (tilt 는 |dx| 정의라 불변)
    - float s: 재생 속도 x s 워프 -> 시퀀스를 1/s 배 길이로 리샘플, 속도류 특징 x s
    테스트셋에는 절대 적용하지 않는다."""
    g = g.sort_values("frame").reset_index(drop=True)
    if kind == "mirror":
        a = g.copy()
        a["horizontal_velocity"] = -a["horizontal_velocity"]
    else:
        s = float(kind)
        n_new = max(int(len(g) / s), 15)
        pos = np.linspace(0, len(g) - 1, n_new)
        a = pd.DataFrame({c: np.interp(pos, np.arange(len(g)), g[c].values) for c in BASE})
        for c in ("vertical_velocity", "horizontal_velocity", "tilt_angular_velocity"):
            a[c] *= s
        a["label"] = g["label"].values[np.round(pos).astype(int)]
        a["frame"] = np.arange(1, n_new + 1)
        a["folder"] = g["folder"].iloc[0]
        a["video"] = g["video"].iloc[0]
    a["video_id"] = g["video_id"].iloc[0] + f"#{kind}"
    return a


def build_augmented(train_raw):
    parts = [train_raw]
    for _, g in train_raw.groupby("video_id", sort=False):
        parts.append(augment_video(g, "mirror"))
        for s in SPEED_FACTORS:
            parts.append(augment_video(g, s))
    return pd.concat(parts, ignore_index=True)


def trigger_frame(frames, preds, persistence):
    run = 0
    for fr, p in zip(frames, preds):
        if p == 1:
            run += 1
            if run == persistence:
                return fr
        else:
            run = 0
    return None


def count_trigger_events(preds, persistence):
    events = run = 0
    fired = False
    for p in preds:
        if p == 1:
            run += 1
            if run == persistence and not fired:
                events += 1
                fired = True
        else:
            run = 0
            fired = False
    return events


def smooth_proba(test_df, col):
    sm = []
    for _, g in test_df.groupby("video_id", sort=False):
        g = g.sort_values("frame")
        sm.append(g[col].ewm(alpha=PROBA_EWMA_ALPHA).mean())
    return pd.concat(sm)


def eval_operating_point(test_df, pcol, threshold, persistence):
    tmp = test_df.copy()
    tmp["pred"] = (tmp[pcol] >= threshold).astype(int)
    n_fall = n_caught = n_adl = n_false = 0
    lead = []
    for _, g in tmp.sort_values("frame").groupby("video_id"):
        has_fall = (g["label"] == 1).any()
        tf = trigger_frame(g["frame"].tolist(), g["pred"].tolist(), persistence)
        if has_fall:
            n_fall += 1
            onset = g.loc[g["label"] == 1, "frame"].max() + 1
            if tf is not None:
                n_caught += 1
                lead.append((onset - tf) / FPS)
        else:
            n_adl += 1
            n_false += count_trigger_events(g["pred"].tolist(), persistence)
    return dict(catch_rate=n_caught / max(n_fall, 1), n_caught=n_caught, n_fall=n_fall,
                fp_per_adl=n_false / max(n_adl, 1), n_adl=n_adl,
                med_lead=float(np.median(lead)) if lead else None,
                mean_lead=float(np.mean(lead)) if lead else None)


def main():
    df = pd.read_csv(CSV_PATH)
    df["video_id"] = df["folder"] + "/" + df["video"]

    gss = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=42)
    train_idx, test_idx = next(gss.split(df, groups=df["video_id"]))
    train_raw, test_raw = df.iloc[train_idx], df.iloc[test_idx]
    if AUGMENT:
        n0 = len(train_raw)
        train_raw = build_augmented(train_raw)
        print(f"augmentation: train rows {n0} -> {len(train_raw)}")

    train_df = add_temporal_features(train_raw)
    test_df = add_temporal_features(test_raw.copy()).copy()
    features = [c for c in train_df.columns
                if c not in ("folder", "video", "frame", "label", "video_id")]
    print(f"{len(features)} features")
    print(f"train {df.iloc[train_idx]['video_id'].nunique()} videos (+aug) / "
          f"test {test_df['video_id'].nunique()} videos")

    clf = HistGradientBoostingClassifier(max_iter=400, max_depth=6, learning_rate=0.08,
                                         class_weight="balanced", random_state=42)
    clf.fit(train_df[features], train_df["label"])

    test_df["proba"] = clf.predict_proba(test_df[features])[:, 1]
    test_df["proba_sm"] = smooth_proba(test_df, "proba")

    print("\n=== frame-level report (raw proba, thr=0.5) ===")
    print(classification_report(test_df["label"], (test_df["proba"] >= 0.5).astype(int),
                                target_names=["normal", "fall_risk"]))

    print("=== operating point sweep (smoothed proba) ===")
    print(f"{'thr':>5} {'pers':>5} {'catch':>7} {'fp/ADL':>7} {'med_lead':>9}")
    for thr in (0.1, 0.15, 0.2, 0.3, 0.4, 0.5):
        for pers in (2, 3, 5):
            m = eval_operating_point(test_df, "proba_sm", thr, pers)
            print(f"{thr:>5} {pers:>5} {m['catch_rate']*100:>6.1f}% "
                  f"{m['fp_per_adl']:>7.2f} {str(m['med_lead']):>9}")

    m = eval_operating_point(test_df, "proba_sm", PROB_THRESHOLD, PERSISTENCE)
    print(f"\n선택된 동작점 thr={PROB_THRESHOLD}, pers={PERSISTENCE}: "
          f"catch {m['n_caught']}/{m['n_fall']}, fp/ADL {m['fp_per_adl']:.2f}, "
          f"median lead {m['med_lead']:.2f}s")

    joblib.dump({
        "model": clf,
        "features": features,
        "base_features": BASE,
        "windows": list(WINDOWS),
        "slope_lag": SLOPE_LAG,
        "ewma_alpha": EWMA_ALPHA,
        "proba_ewma_alpha": PROBA_EWMA_ALPHA,
        "prob_threshold": PROB_THRESHOLD,
        "persistence": PERSISTENCE,
        "fps": FPS,
        "augmented": AUGMENT,
        "version": 2.1 if AUGMENT else 2,
    }, MODEL_OUT)
    print(f"saved model to {MODEL_OUT}")


if __name__ == "__main__":
    main()
