"""
Evidence report for the "pre-fall prediction" claim.

Re-creates the exact same held-out test split used in train_classifier.py (same
GroupShuffleSplit + random_state, so this is genuinely unseen data, not the training set),
then for each candidate operating point reports:
  - frame-level precision/recall
  - per-video catch rate (did we flag risk at least once before the fall) and false-alarm
    rate (events per ADL-only video)
  - LEAD TIME: for every fall we caught, how many seconds before the actual fall onset did
    the system raise the flag. This is the number that actually proves "pre-fall", not just
    "fall", detection.

Outputs:
  - model_training/evaluation_report.md   (numbers + a short plain-language summary)
  - model_training/evaluation_charts.png  (catch-rate/false-alarm trade-off + lead-time histogram)
"""
import os
import glob
import cv2
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import classification_report
import joblib

# Paths are set up to work when this file lives in fall_detection_DL/model_training/ :
#   - the trained model is read from the repo root (fall_detection_DL/fall_risk_model.joblib)
#   - the Le2i features/videos are read from wherever you downloaded the dataset -- change
#     DATA_ROOT below if it's not in this default location on your machine
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_ROOT = os.path.expanduser("~/Documents/Claude/Projects/FallDetection/data/le2i")
CSV_PATH = os.path.join(DATA_ROOT, "features.csv")
MODEL_PATH = os.path.join(REPO_ROOT, "fall_risk_model.joblib")
OUT_DIR = SCRIPT_DIR
REPORT_MD = os.path.join(OUT_DIR, "evaluation_report.md")
CHART_PNG = os.path.join(OUT_DIR, "evaluation_charts.png")

FEATURES = ["vertical_velocity", "horizontal_velocity", "tilt_angle_deg", "tilt_angular_velocity"]
CANDIDATE_POINTS = [(0.5, 3), (0.6, 3), (0.7, 3), (0.5, 5)]  # (prob_threshold, persistence)

bundle = joblib.load(MODEL_PATH)
clf = bundle["model"]

df = pd.read_csv(CSV_PATH)
df["video_id"] = df["folder"] + "/" + df["video"]

gss = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=42)
train_idx, test_idx = next(gss.split(df, groups=df["video_id"]))
test_df = df.iloc[test_idx].copy()
test_df["proba"] = clf.predict_proba(test_df[FEATURES])[:, 1]

# fps per video, needed to turn "lead time in frames" into "lead time in seconds"
fps_cache = {}
def get_fps(video_id):
    if video_id in fps_cache:
        return fps_cache[video_id]
    folder, video = video_id.split("/", 1)
    base = os.path.join(DATA_ROOT, folder, folder)
    path = glob.glob(os.path.join(base, "Videos", video))
    fps = 25.0
    if path:
        cap = cv2.VideoCapture(path[0])
        f = cap.get(cv2.CAP_PROP_FPS)
        if f and f > 0:
            fps = f
        cap.release()
    fps_cache[video_id] = fps
    return fps


def count_trigger_frame(frames, preds, persistence):
    """Return the frame number at which a run of >=persistence consecutive risky
    predictions first completes, or None if it never does."""
    run = 0
    for fr, p in zip(frames, preds):
        if p == 1:
            run += 1
            if run == persistence:
                return fr
        else:
            run = 0
    return None


results = []
lead_times_by_point = {}
for threshold, persistence in CANDIDATE_POINTS:
    test_df["pred"] = (test_df["proba"] >= threshold).astype(int)
    n_fall = n_caught = n_adl = n_false_events = 0
    lead_times = []
    for vid, g in test_df.sort_values("frame").groupby("video_id"):
        has_fall = (g["label"] == 1).any()
        frames = g["frame"].tolist()
        preds = g["pred"].tolist()
        trigger_frame = count_trigger_frame(frames, preds, persistence)
        if has_fall:
            n_fall += 1
            onset_frame = g.loc[g["label"] == 1, "frame"].max() + 1
            if trigger_frame is not None:
                n_caught += 1
                fps = get_fps(vid)
                lead_times.append((onset_frame - trigger_frame) / fps)
        else:
            n_adl += 1
            # count discrete false-alarm events (a fresh run each time it re-completes)
            run = 0
            events = 0
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
            n_false_events += events
    results.append({
        "threshold": threshold, "persistence": persistence,
        "n_fall_videos": n_fall, "n_caught": n_caught,
        "catch_rate": n_caught / max(n_fall, 1),
        "n_adl_videos": n_adl, "false_events_per_adl_video": n_false_events / max(n_adl, 1),
        "mean_lead_time_s": float(np.mean(lead_times)) if lead_times else None,
        "median_lead_time_s": float(np.median(lead_times)) if lead_times else None,
        "min_lead_time_s": float(np.min(lead_times)) if lead_times else None,
    })
    lead_times_by_point[(threshold, persistence)] = lead_times

results_df = pd.DataFrame(results)
print(results_df.to_string(index=False))

# frame-level report at the operating point actually saved in the model bundle
saved_threshold, saved_persistence = bundle["prob_threshold"], bundle["persistence"]
saved_pred = (test_df["proba"] >= saved_threshold).astype(int)
frame_report = classification_report(test_df["label"], saved_pred, target_names=["normal", "fall_risk"])
print("\nframe-level report at saved operating point "
      f"(threshold={saved_threshold}, persistence={saved_persistence}):\n", frame_report)

# --- charts ---
fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))

ax = axes[0]
ax.plot(results_df["false_events_per_adl_video"], results_df["catch_rate"] * 100, "o-", color="#d1495b")
for _, row in results_df.iterrows():
    ax.annotate(f"thr={row.threshold}\npers={row.persistence}",
                (row.false_events_per_adl_video, row.catch_rate * 100),
                fontsize=8, xytext=(5, 5), textcoords="offset points")
ax.set_xlabel("False alarms per ADL-only video")
ax.set_ylabel("Fall catch rate (%)")
ax.set_title("Catch rate vs. false-alarm trade-off")
ax.grid(alpha=0.3)

ax = axes[1]
best_point = max(CANDIDATE_POINTS, key=lambda p: (
    [r for r in results if r["threshold"] == p[0] and r["persistence"] == p[1]][0]["catch_rate"]))
lt = lead_times_by_point[best_point]
ax.hist(lt, bins=12, color="#2e86ab", edgecolor="white")
ax.axvline(0, color="black", linewidth=1)
ax.set_xlabel("Lead time (seconds before actual fall onset)")
ax.set_ylabel("Number of caught falls")
ax.set_title(f"Warning lead time (thr={best_point[0]}, persistence={best_point[1]})")
ax.grid(alpha=0.3)

plt.tight_layout()
plt.savefig(CHART_PNG, dpi=150)
print(f"\nsaved chart to {CHART_PNG}")

# --- markdown report ---
with open(REPORT_MD, "w") as f:
    f.write("# Fall-risk model evaluation (held-out test set)\n\n")
    f.write(f"Test set: {test_df['video_id'].nunique()} videos never seen during training "
            f"({int(results_df.iloc[0].n_fall_videos)} with a fall, "
            f"{int(results_df.iloc[0].n_adl_videos)} ADL-only).\n\n")
    f.write("## Operating point sweep\n\n")
    f.write(results_df.to_markdown(index=False))
    f.write("\n\n## Frame-level report (saved operating point: "
            f"threshold={saved_threshold}, persistence={saved_persistence})\n\n```\n")
    f.write(frame_report)
    f.write("```\n\n## What this shows\n\n")
    best = results_df.iloc[(results_df["catch_rate"] - 1.0).abs().argsort()].iloc[0]
    f.write(
        f"- At threshold={best.threshold}, persistence={best.persistence}: caught "
        f"{int(best.n_caught)}/{int(best.n_fall_videos)} falls in the test set "
        f"({best.catch_rate*100:.0f}%), with {best.false_events_per_adl_video:.2f} false "
        f"alarms per ADL-only video.\n"
        f"- Median warning lead time for caught falls: "
        f"{best.median_lead_time_s:.2f} seconds before the person actually started falling "
        f"(min observed: {best.min_lead_time_s:.2f}s).\n"
        f"- This is on Le2i test videos never used in training (split by video, not by frame, "
        f"so there is no data leakage between train and test).\n"
        f"- Caveat: small test set ({int(best.n_adl_videos)} ADL videos), so the false-alarm "
        f"rate has wide uncertainty. Treat this as a proof-of-concept result, not a certified "
        f"accuracy figure.\n"
    )
print(f"saved report to {REPORT_MD}")
