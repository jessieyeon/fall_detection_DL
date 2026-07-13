import facial_recognition as fr

import sys
import os
import csv
import cv2
import mediapipe as mp
from time import time
from datetime import datetime
from collections import deque

VELOCITY_THRESHOLD = 1.2   # torso drop speed (frame-heights/sec) that counts as a fall risk - tune by testing
SMOOTHING_WINDOW = 3       # frames averaged to reduce landmark jitter
RISK_COOLDOWN = 3.0        # seconds to wait before raising another risk signal for the same fall
LOG_FILE = "fall_risk_log.csv"


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


def torsoCenterY(landmarks):
    # average of shoulders + hips approximates center of mass better than shoulders alone
    left_shoulder_y = landmarks[11][1]
    right_shoulder_y = landmarks[12][1]
    left_hip_y = landmarks[23][1]
    right_hip_y = landmarks[24][1]
    return (left_shoulder_y + right_shoulder_y + left_hip_y + right_hip_y) / 4


def send_fall_risk_signal(name):
    # TODO: wire this up to the actual impact-mitigation tile (HTTP request / MQTT / serial, etc.)
    print(f"[FALL RISK] Rapid collapse motion detected (person: {name}) -> tile signal sent")


def log_fall_risk_event(name, velocity):
    file_exists = os.path.isfile(LOG_FILE)
    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "person", "velocity"])
        writer.writerow([datetime.now().isoformat(timespec="seconds"), name, f"{velocity:.3f}"])


# usage: python main.py [video_path]   (defaults to webcam 0 if no path is given)
video_source = 0
if len(sys.argv) > 1:
    video_source = int(sys.argv[1]) if sys.argv[1].isdigit() else sys.argv[1]

frr = fr.FaceRecognition()
frr.encode_faces()
pose_video = mp.solutions.pose.Pose(static_image_mode=False, min_detection_confidence=0.7, model_complexity=1)
video = cv2.VideoCapture(video_source)

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

velocity_history = deque(maxlen=SMOOTHING_WINDOW)
previous_center_y = None
previous_time = None
last_risk_time = 0
current_face_name = "unknown"

while video.isOpened():
    ret, frame = video.read()
    if not ret:
        break

    height, _, _ = frame.shape
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
    smoothed_velocity = 0.0

    if landmarks is not None:
        center_y = torsoCenterY(landmarks)

        if previous_center_y is not None:
            dt = now - previous_time
            if dt > 0:
                # normalize by frame height so the threshold doesn't depend on resolution/camera distance
                velocity = ((center_y - previous_center_y) / height) / dt
                velocity_history.append(velocity)
                smoothed_velocity = sum(velocity_history) / len(velocity_history)

                if smoothed_velocity > VELOCITY_THRESHOLD and (now - last_risk_time) > RISK_COOLDOWN:
                    print(f"Fall risk! torso dropping at {smoothed_velocity:.2f} frame-heights/sec")
                    send_fall_risk_signal(current_face_name)
                    log_fall_risk_event(current_face_name, smoothed_velocity)
                    last_risk_time = now

        previous_center_y = center_y
        previous_time = now
    else:
        # lost tracking - drop stale velocity history so old motion doesn't linger
        velocity_history.clear()
        previous_center_y = None
        previous_time = None

    cv2.putText(modified_frame, f"velocity: {smoothed_velocity:.2f}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
    cv2.imshow('Pose Landmarks', modified_frame)

    k = cv2.waitKey(1) & 0xFF
    if k == 27:
        break

video.release()
cv2.destroyAllWindows()
