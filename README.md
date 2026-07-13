# Fall Detection using OpenCV and MediaPipe
This project is aimed at developing a fall detection system using OpenCV and MediaPipe libraries in Python. The system detects falls by monitoring the movements of individuals captured in live video feeds and triggers an alert when a fall is detected. The implementation involves capturing the video using OpenCV, marking landmarks using MediaPipe, and analyzing the movements to identify falls.

## Requirements
On macOS, `face_recognition` builds `dlib` from source, so install `cmake` first:

```
brew install cmake
```

Then install the pinned Python dependencies:

```
pip install -r requirements.txt
```

`mediapipe` is pinned to `0.10.14` because newer releases removed the legacy
`mp.solutions.pose` API this project depends on.

## Usage

```
python main.py               # live webcam
python main.py path/to/video.mp4   # recorded video (for testing without a webcam)
```

### Per-tile targeting (which impact-mitigation tile fires)

Tiles are laid out in a grid on the floor. `main.py` maps the detected person's foot
position to a grid cell (row/col) and only signals the tile at that cell, numbered
`0..rows*cols-1` in row-major order (row 0 left-to-right, then row 1, ...).

Run the calibration tool once per camera setup (whenever the camera or tile grid moves):

```
python calibrate.py <rows> <cols> [video_source]
# e.g. python calibrate.py 2 3          -> a 2x3 grid, using the webcam
```

Click the 4 corners of the tile-covered floor area in the video frame, in order:
top-left, top-right, bottom-right, bottom-left. This writes `calibration.json`
(gitignored, since it's specific to one physical camera/tile setup). If it's
missing, `main.py` still runs but always targets tile 0.

### Arduino / servo signal

Set `SERIAL_PORT` near the top of `main.py` to the Arduino's serial port
(e.g. `/dev/tty.usbmodemXXXX` on macOS, `COM3` on Windows) once it's wired up.
Each fall-risk signal sends the tile number as a line of text (e.g. `"3\n"`)
over serial; the Arduino firmware reads that number and moves the matching
servo. Without an Arduino connected (or `SERIAL_PORT` left as `None`), signals
are just printed to the console so the rest of the pipeline can still be tested.

### Working of the Prototype
[Working Demo with Fall Detection and Face Recognition](https://drive.google.com/file/d/1HhNCq11J1ZNmuDoxo6KYVFS1S7IJZid7/view?usp=sharing)

## How it works

### Video Capture: 
The system captures live video using OpenCV, allowing it to monitor individuals in real-time.

### Landmark Detection: 
MediaPipe library is used to detect landmarks on the human body, such as shoulders, elbows, and hips. These landmarks help in tracking the movements of individuals in the video.

### Fall Detection Algorithm: 
The system periodically checks the previous coordinates of the shoulders of the person in the frame, typically every 4 seconds. If there is a significant drop in the height of the shoulders, it indicates a potential fall.

### Face Detection:
Facial recognition using the facial_recognition library helps identify individuals in the video. This information is then used to retrieve contextual data from the integrated database about the person who has fallen.

### Alert Triggering:
When a fall is detected, the system prints "Fall Detected" and retrieves relevant information about the individual from the database. This information includes medical history, emergency contact details, and specific care instructions.

### Integration with Healthcare Authorities and Guardians:
The database contains comprehensive information about the individuals being monitored, securely storing their medical history and emergency contact details. Healthcare authorities and guardians receive immediate notifications via Telegram with detailed information about the incident, enabling them to initiate a timely response. Healthcare authorities coordinate assistance efforts based on the information provided, dispatching appropriate medical personnel or emergency responders to the location.

