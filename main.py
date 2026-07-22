import facial_recognition as fr
import calibration

import sys
import os
import csv
import math
import cv2
import numpy as np
import mediapipe as mp
import serial
import joblib
from time import time
from datetime import datetime
from collections import deque

# ---- legacy single-threshold fallback (used only if the trained model file is missing) ----
VELOCITY_THRESHOLD = 1.2   # torso drop speed (frame-heights/sec) that counts as a fall risk

# ---- trained pre-fall risk model (see model_training/train_classifier.py) ----
MODEL_FILE = "fall_risk_model.joblib"  # lives next to main.py (repo root)
PERSISTENCE = 3             # consecutive risky frames required before firing (suppresses jitter)
FALLBACK_PROB_THRESHOLD = 0.7  # overridden by the threshold saved inside the model file

SMOOTHING_WINDOW = 3        # frames averaged to reduce landmark jitter
RISK_COOLDOWN = 3.0         # seconds to wait before raising another risk signal for the same fall
RESET_DELAY = 2.0           # seconds after firing before sending the "return to home" signal
                             # (the Adafruit-PWM Arduino sketch doesn't auto-reset like the old one did)
LOG_FILE = "fall_risk_log.csv"

SERIAL_PORT = "/dev/cu.usbmodem9888E00A2B282"  # macOS Arduino Uno R4 WiFi port
SERIAL_BAUDRATE = 9600

L_SHOULDER, R_SHOULDER = 11, 12
L_HIP, R_HIP = 23, 24


def load_risk_model():
    if not os.path.isfile(MODEL_FILE):
        print(f"Warning: {MODEL_FILE} not found - falling back to the single vertical-velocity "
              f"threshold ({VELOCITY_THRESHOLD}). Run model_training/train_classifier.py and copy "
              "the .joblib file next to main.py to use the trained model instead.")
        return None
    bundle = joblib.load(MODEL_FILE)
    print(f"Loaded fall-risk model (threshold={bundle['prob_threshold']}, "
          f"persistence={bundle['persistence']} frames)")
    return bundle


def detectPose(frame, pose_model):
    modified_frame = frame.copy()
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = pose_model.process(frame_rgb)
    height, width, _ = frame.shape
    landmarks = []
    if results.pose_landmarks:
        for landmark in results.pose_landmarks.landmark:
            landmarks.append((int(landmark.x * width), int(landmark.y * height),
                              (landmark.z * width)))
        connections = mp.solutions.pose.POSE_CONNECTIONS
        for connection in connections:
            start_point = connection[0]
            end_point = connection[1]
            cv2.line(modified_frame, (landmarks[start_point][0], landmarks[start_point][1]),
                     (landmarks[end_point][0], landmarks[end_point][1]), (0, 255, 0), 3)
    else:
        return modified_frame, None
    return modified_frame, landmarks


def torsoPoints(landmarks):
    # same definition used by model_training/extract_features.py -- keep these two in sync,
    # otherwise the live features won't match what the model was trained on (train/serve skew)
    sx = (landmarks[L_SHOULDER][0] + landmarks[R_SHOULDER][0]) / 2
    sy = (landmarks[L_SHOULDER][1] + landmarks[R_SHOULDER][1]) / 2
    hx = (landmarks[L_HIP][0] + landmarks[R_HIP][0]) / 2
    hy = (landmarks[L_HIP][1] + landmarks[R_HIP][1]) / 2
    return (sx, sy), (hx, hy)


def tiltAngleDeg(shoulder_c, hip_c):
    dx = hip_c[0] - shoulder_c[0]
    dy = hip_c[1] - shoulder_c[1]
    return math.degrees(math.atan2(abs(dx), abs(dy) + 1e-6))


def torsoCenterXY(shoulder_c, hip_c):
    return ((shoulder_c[0] + hip_c[0]) / 2, (shoulder_c[1] + hip_c[1]) / 2)


def footPosition(landmarks):
    # midpoint of both ankles approximates where the person's feet touch the floor
    left_ankle = landmarks[27]
    right_ankle = landmarks[28]
    return ((left_ankle[0] + right_ankle[0]) / 2, (left_ankle[1] + right_ankle[1]) / 2)


def connect_arduino():
    if not SERIAL_PORT:
        print("No SERIAL_PORT configured - running in simulation mode (signals will only be printed).")
        return None
    try:
        connection = serial.Serial(SERIAL_PORT, SERIAL_BAUDRATE, timeout=1)
        print(f"Connected to Arduino on {SERIAL_PORT}")
        return connection
    except serial.SerialException as e:
        print(f"Warning: could not open {SERIAL_PORT} ({e}) - running in simulation mode.")
        return None


def send_fall_risk_signal(name, tile_index, arduino):
    # main.py numbers tiles 0..3, but the Arduino sketch (Adafruit PCA9685 driver) numbers
    # motors 1..4 and reads a single character (not a newline-terminated integer), so tile 0
    # -> "1", tile 1 -> "2", etc.
    motor_id = tile_index + 1
    if arduino is not None:
        arduino.write(str(motor_id).encode())
        print(f"[FALL RISK] tile={tile_index} (motor {motor_id}) person={name} -> sent to Arduino")
    else:
        print(f"[FALL RISK] tile={tile_index} (motor {motor_id}) person={name} -> "
              "signal sent (simulated, no Arduino connected)")


def send_reset_signal(arduino):
    # tells the Arduino sketch to return every "fired" motor back to HOME_ANGLE
    if arduino is not None:
        arduino.write(b"0")
        print("[RESET] sent to Arduino")
    else:
        print("[RESET] signal sent (simulated, no Arduino connected)")


def log_fall_risk_event(name, tile_index, score):
    file_exists = os.path.isfile(LOG_FILE)
    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "person", "tile", "risk_score"])
        writer.writerow([datetime.now().isoformat(timespec="seconds"), name, tile_index, f"{score:.3f}"])


# usage: python main.py [video_path]   (defaults to webcam 0 if no path is given)
video_source = 0
if len(sys.argv) > 1:
    video_source = int(sys.argv[1]) if sys.argv[1].isdigit() else sys.argv[1]

frr = fr.FaceRecognition()
frr.encode_faces()
pose_video = mp.solutions.pose.Pose(static_image_mode=False, min_detection_confidence=0.7, model_complexity=1)
video = cv2.VideoCapture(video_source)
tile_grid = calibration.load_tile_grid()
arduino = connect_arduino()
risk_model = load_risk_model()
prob_threshold = risk_model["prob_threshold"] if risk_model else FALLBACK_PROB_THRESHOLD
persistence = risk_model["persistence"] if risk_model else PERSISTENCE

# Processing a recorded video file (esp. with face_recognition) is slower than the file's own frame rate,
# so wall-clock time between reads no longer matches the time between frames in the footage. For a local
# file, advance a virtual clock using the file's own fps instead. A live source - a webcam index or a
# network camera stream URL (e.g. a phone IP-camera app) - delivers frames in real time either way, so
# wall-clock time is correct there.
is_video_file = isinstance(video_source, str) and os.path.isfile(video_source)
if is_video_file:
    source_fps = video.get(cv2.CAP_PROP_FPS)
    if not source_fps or source_fps <= 0:
        source_fps = 30.0
    video_clock = 0.0

vy_hist = deque(maxlen=SMOOTHING_WINDOW)
vx_hist = deque(maxlen=SMOOTHING_WINDOW)
tilt_hist = deque(maxlen=SMOOTHING_WINDOW)
prev_center = None
prev_tilt = None
prev_time = None
consecutive_risk_frames = 0
last_risk_time = 0
reset_pending = False
current_face_name = "unknown"

while video.isOpened():
    ret, frame = video.read()
    if not ret:
        break

    height, width, _ = frame.shape
    modified_frame, landmarks = detectPose(frame, pose_video)

    face_name = frr.recognize_face(frame)
    if face_name is not None:
        current_face_name = face_name
        print("Detected face:", face_name)

    if is_video_file:
        video_clock += 1.0 / source_fps
        now = video_clock
    else:
        now = time()

    risk_score = 0.0
    current_row, current_col, current_tile = None, None, 0

    if landmarks is not None:
        shoulder_c, hip_c = torsoPoints(landmarks)
        center = torsoCenterXY(shoulder_c, hip_c)
        tilt = tiltAngleDeg(shoulder_c, hip_c)

        if tile_grid is not None:
            foot_xy = footPosition(landmarks)
            current_row, current_col, current_tile = calibration.pixel_to_tile(foot_xy, tile_grid)

        vy = vx = tilt_vel = 0.0
        if prev_center is not None and prev_time is not None:
            dt = now - prev_time
            if dt > 0:
                vy = (center[1] - prev_center[1]) / height / dt
                vx = (center[0] - prev_center[0]) / width / dt
                vy_hist.append(vy)
                vx_hist.append(vx)
                vy = sum(vy_hist) / len(vy_hist)
                vx = sum(vx_hist) / len(vx_hist)
        if prev_tilt is not None and prev_time is not None:
            dt = now - prev_time
            if dt > 0:
                tilt_vel = (tilt - prev_tilt) / dt
        tilt_hist.append(tilt)

        if risk_model is not None:
            features = [[vy, vx, tilt, tilt_vel]]
            risk_score = risk_model["model"].predict_proba(features)[0][1]
            is_risky_frame = risk_score >= prob_threshold
        else:
            risk_score = vy  # legacy behavior: report velocity magnitude as the "score"
            is_risky_frame = vy > VELOCITY_THRESHOLD

        if is_risky_frame:
            consecutive_risk_frames += 1
        else:
            consecutive_risk_frames = 0

        if consecutive_risk_frames >= persistence and (now - last_risk_time) > RISK_COOLDOWN:
            print(f"Fall risk! score={risk_score:.2f} (persisted {consecutive_risk_frames} frames)")
            send_fall_risk_signal(current_face_name, current_tile, arduino)
            log_fall_risk_event(current_face_name, current_tile, risk_score)
            last_risk_time = now
            consecutive_risk_frames = 0
            reset_pending = True

        prev_center = center
        prev_tilt = tilt
        prev_time = now
    else:
        # lost tracking - drop stale history so old motion doesn't linger
        vy_hist.clear()
        vx_hist.clear()
        tilt_hist.clear()
        prev_center = None
        prev_tilt = None
        prev_time = None
        consecutive_risk_frames = 0

    if reset_pending and (now - last_risk_time) > RESET_DELAY:
        send_reset_signal(arduino)
        reset_pending = False

    if tile_grid is not None:
        calibration.draw_tile_grid(modified_frame, tile_grid, {current_tile} if current_row is not None else None)

    cv2.putText(modified_frame, f"risk: {risk_score:.2f} ({consecutive_risk_frames}/{persistence})",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
    cv2.imshow('Pose Landmarks', modified_frame)

    k = cv2.waitKey(1) & 0xFF
    if k == 27:
        break

video.release()
cv2.destroyAllWindows()
if arduino is not None:
    arduino.close()
