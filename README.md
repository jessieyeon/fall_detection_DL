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
python main.py                                  # 웹캠
python main.py test_videos/S01T13R01_.mp4       # 녹화 영상
python main.py --port /dev/cu.usbmodemXXXX      # 아두이노 연결
python main.py --profile doll                   # 인형 프로파일
python main.py --no-serial                      # 임계값 튜닝용 (서보 안 움직임)
python main.py --face-every 10                  # 10프레임마다 얼굴 인식
```

얼굴 인식은 기본으로 꺼져 있습니다(`--face-every 0`). `face_recognition` 은 무거워서
프레임레이트를 크게 떨어뜨리고, 프레임레이트가 떨어지면 빠르게 쓰러지는 대상에서
`persistence` 프레임 수를 채우지 못합니다.

### 판정 프로파일

낙상 판정 파라미터는 `profiles.json` 에 있습니다. 코드 상수로 두지 않는 이유는
리허설 중에 코드를 고치면 시연 당일 잘못된 값이 남기 때문입니다.

| 항목 | 뜻 |
|---|---|
| `persistence` | 발사하기까지 필요한 연속 위험 프레임 수 |
| `prob_threshold` | 낙상 위험으로 볼 모델 확률 |
| `window` | 방향 평균을 낼 프레임 수 |
| `tau_R` | 이 값 미만이면 방향 판정 불가 → 전체 타일 |
| `tau_R_strict` | 이 값 이상이고 대각 정중앙이면 모서리 1장만 |
| `tau_lean` | 이 값 미만이면 수직 붕괴로 보고 전체 타일 |

`tau_*` 세 값은 물리 상수가 아니라 연출값입니다. `--no-serial` 로 25~30회
리허설한 뒤 `fall_risk_log.csv` 의 `lean_ratio` 와 `R` 분포를 보고 정합니다.
자세한 절차는 설계 문서 §10.3을 참고하세요.

### Per-tile targeting (which impact-mitigation tile fires)

Tiles are laid out in a grid on the floor, numbered `0..rows*cols-1` in row-major
order (row 0 left-to-right, then row 1, ...). `main.py` does **not** use the
detected person's foot position to pick a tile — ankle landmarks are unreliable
in this setup (easily occluded, poorly tracked on the doll), so the design
deliberately avoids them. Instead the fall's *direction* — **which way the body
moves in the image** (the torso center's motion, `vx`/`vy`) — and its agreement
across the recent frame window decide the tiles: a clear cardinal direction fires
a whole row/column (2 tiles), a clear diagonal fires 3 tiles (everything but the
far corner), a very confident diagonal fires a single corner tile, and a
low-confidence or mostly-vertical reading fires every tile (1 to 4 tiles total,
see `tiles.select_tiles`).

**Camera placement matters.** Near/far (toward vs away from the camera) is read
from vertical image motion, so the camera must look **down at the floor from an
elevated, oblique angle** (like a high room corner) — the same viewpoint the
Le2i training videos use. A front, eye-level camera cannot tell a forward fall
from a backward one (both just foreshorten in 2D), which collapses every fall to
the "near" direction and leaves the far-row tiles unused. A direct top-down
(bird's-eye) view is also wrong — MediaPipe pose estimation breaks there. Set
`camera_yaw_deg` in `calibration.json` if the grid looks rotated in frame.

Run the calibration tool once per camera setup (whenever the camera or tile grid moves):

```
python calibrate.py <rows> <cols> [video_source]
# e.g. python calibrate.py 2 3          -> a 2x3 grid, using the webcam
```

Click the 4 corners of the tile-covered floor area in the video frame, in order:
top-left, top-right, bottom-right, bottom-left. This writes `calibration.json`
(gitignored, since it's specific to one physical camera/tile setup). If it's
missing, `main.py` still runs, falls back to a 2x2 grid, and simply skips
drawing the grid overlay on screen.

`calibration.json` 에는 `camera_yaw_deg` 항목이 함께 저장됩니다. 카메라가 타일
격자를 정면에서 보고 있으면 `0` 그대로 두고, 격자가 화면상 회전해 보이면 그
각도(도, 시계방향 양수)를 손으로 넣습니다. 낙상 방향을 격자 좌표계로 옮길 때
사용됩니다.

### 아두이노 / 서보 신호

`--port` 로 시리얼 포트를 지정합니다(예: macOS `/dev/cu.usbmodemXXXX`,
Windows `COM3`). 생략하면 시뮬레이션 모드로 동작하며 신호는 콘솔에만 찍힙니다.

프로토콜은 줄 단위 텍스트이고 보율은 115200입니다.

| 파이썬 → 아두이노 | 아두이노 → 파이썬 |
|---|---|
| `FIRE 1,3` | `OK FIRE 1,3` |
| `RESET` | `OK RESET` |
| `PING` | `OK PING` |
| — | `READY 4` (부팅 완료 시) |
| — | `ERR <사유>` |
| — | `# <주석, 무시됨>` |

타일 번호는 어디서나 0-indexed 입니다. 타일 번호와 PCA9685 채널의 매핑은
`.ino` 안에만 있습니다.

시리얼 모니터(115200, 줄 끝 "새 줄")에서 `FIRE 1,3` 을 직접 입력하면 파이썬 없이
하드웨어만 시험할 수 있습니다. 서보 4개 동시 기동은 `FIRE 0,1,2,3` 으로
확인하세요 — 전원 용량이 부족하면 보드가 리셋됩니다.

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

