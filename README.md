# Fall Detection using OpenCV and MediaPipe
This project is aimed at developing a fall detection system using OpenCV and MediaPipe libraries in Python. The system detects falls by monitoring the movements of individuals captured in live video feeds and triggers an alert when a fall is detected. The implementation involves capturing the video using OpenCV, marking landmarks using MediaPipe, and analyzing the movements to identify falls.

## 빠른 시작 — 다온 웹 플랫폼

이 저장소에는 CV 파이프라인(`main.py`) 위에 얹은 **다온 케어 웹 플랫폼**(`webservice/`)이 들어 있습니다. 아래 순서대로 하면 클론한 뒤 바로 띄울 수 있습니다.

> 빌드 산출물(`webservice/frontend/dist/`), 계정 DB(`webservice/daon.db`), `node_modules/`, YOLO 가중치(`*.pt`)는 gitignore라 저장소에 없습니다. 그래서 **프런트 빌드 + DB 시드**를 직접 해야 합니다.

```bash
# 1) 클론 + 파이썬 의존성  (macOS는 먼저 `brew install cmake`)
git clone https://github.com/jessieyeon/fall_detection_DL.git
cd fall_detection_DL
git checkout feature/daon-web-platform
pip install -r requirements.txt

# 2) 프런트엔드 빌드  (이게 없으면 서버가 빈 화면)
cd webservice/frontend && npm install && npm run build && cd ../..

# 3) 데모 계정 DB 시드
python3 -m webservice.seed        # senior@daon.com / guardian@daon.com (둘 다 비번 pw)

# 4) 서버 실행 → 브라우저에서 http://localhost:8000
python3 -m uvicorn webservice.app:app --port 8000
```

**한 번에 실행 (권장)**: 위 1~3은 최초 1회만 하면 됩니다. 그다음부터는 웹앱 + 감지
파이프라인 + 아두이노를 한 줄로 띄웁니다(아두이노 포트 자동 탐지, Ctrl-C 로 전부 종료):

```bash
./run.sh
# 포트 직접 지정:   PORT=/dev/cu.usbmodemXXXX ./run.sh
# 녹화 영상 사용:   SOURCE=test_videos/S01T13R01_.mp4 ./run.sh
```

포트를 못 찾으면 서보 없이(시뮬레이션) 앱만 계속 돕니다. (Windows에서는 bash가 없어
`./run.sh` 대신 4번 uvicorn 과 `py main.py --port COM3 --live-url ...` 를 각각 실행하세요.)

- **YOLO 가중치**(`yolo11m.pt`)는 컨설팅 첫 분석 때 자동 다운로드됩니다.
- **실시간 중계**에 실제 카메라를 흘려보내려면 별도 터미널에서:
  `python main.py --live-url http://localhost:8000`
  - 아두이노(타일/덮개)까지 붙이려면 `--port` 추가: `python main.py --port <포트> --live-url http://localhost:8000`
  - 포트 이름은 컴퓨터마다 다릅니다. macOS `ls /dev/cu.usbmodem*`, Linux `ls /dev/ttyACM*`, Windows 장치 관리자 "포트(COM & LPT)" (또는 Arduino IDE `도구 → 포트`)로 확인. 코드에 하드코딩된 포트는 없어 실행 시 값만 바꾸면 됩니다. 자세한 표는 아래 [아두이노 / 서보 신호](#아두이노--서보-신호) 참고.
- 자세한 시연 절차·구성도는 [DEMO_PREP.md](DEMO_PREP.md), 프런트엔드 개발 과정은 [FRONTEND.md](FRONTEND.md) 참고.

**Windows 참고**
- `python3` 대신 `python` 또는 `py`를 씁니다. 예: `py -m webservice.seed`, `py -m uvicorn webservice.app:app --port 8000`.
- `brew install cmake`는 macOS 전용입니다. `requirements.txt`의 `face_recognition`은 dlib를 소스 빌드해서 CMake + Visual Studio C++ Build Tools가 필요합니다. **웹 플랫폼은 `face_recognition`을 쓰지 않으므로**(얼굴인식은 `main.py --face-every` 옵션 전용, 기본 꺼짐), 웹 데모만 볼 거면 `requirements.txt`에서 `face_recognition==1.3.0` 줄을 지우고 `pip install -r requirements.txt` 하면 됩니다.
- `npm install && npm run build` 등 나머지 명령은 PowerShell/cmd에서 동일하게 동작합니다. 아두이노 포트만 `/dev/cu.usbmodemXXXX` 대신 `COM3` 형식입니다.

아래 내용은 CV 파이프라인(`main.py`, 아두이노/서보) 자체에 대한 설명입니다.

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

`--port` 로 시리얼 포트를 지정합니다. 생략하면 시뮬레이션 모드로 동작하며 신호는
콘솔에만 찍힙니다. **포트 이름은 코드에 하드코딩돼 있지 않으므로**, 컴퓨터·USB 자리가
바뀌면 실행할 때 아래 방법으로 확인해 `--port` 값만 바꿔 넣으면 됩니다:

| OS | 포트 찾기 | 예시 |
|---|---|---|
| macOS | `ls /dev/cu.usbmodem*` | `/dev/cu.usbmodemXXXX` |
| Linux | `ls /dev/ttyACM*` | `/dev/ttyACM0` |
| Windows | 장치 관리자 → 포트(COM & LPT) | `COM3` |

제일 확실한 방법은 Arduino IDE `도구 → 포트` 에 체크된 이름을 그대로 쓰는 것입니다.
이 프로젝트 보드는 **Arduino UNO R4 WiFi** 입니다 — 네이티브 USB라 업로드가
"No device found" 로 실패하면 보드의 RESET 을 빠르게 두 번(더블탭) 눌러 부트로더
(L LED가 숨쉬듯 깜빡임)에 넣은 뒤 업로드합니다.

프로토콜은 줄 단위 텍스트이고 보율은 115200입니다.

| 파이썬 → 아두이노 | 아두이노 → 파이썬 |
|---|---|
| `FIRE 1,3` | `OK FIRE 1,3` |
| `RESET` | `OK RESET` |
| `PING` | `OK PING` |
| — | `READY 4` (부팅 완료 시) |
| — | `ERR <사유>` |
| — | `# <주석, 무시됨>` |

타일 번호는 어디서나 0-indexed 입니다. 서보는 물리적으로 **8개**입니다 — 타일 4개는
PCA9685 채널 **1,3,5,7**, 각 타일의 덮개 서보 4개는 채널 **2,4,6,8**(타일 `i` 와 세트)에
연결됩니다. `FIRE` 시 덮개를 90도 **먼저** 열고 잠깐(`SEQ_DELAY_MS`, 기본 200ms) 뒤
타일을 올리며, `RESET` 은 역순(타일 내림 → 덮개 닫음)으로 처리해 내려가는 타일이 닫히는
덮개에 걸리지 않게 합니다. `READY` 가 보고하는 개수는 타일 수(4)입니다. 채널 매핑과
각도·타이밍 상수는 모두 `.ino` 안에 있습니다.

시리얼 모니터(115200, 줄 끝 "새 줄")에서 `FIRE 0` 을 직접 입력하면 파이썬 없이
하드웨어만 시험할 수 있습니다(→ ch2 덮개 열림 → ch1 타일 상승, 이어 `RESET`). 서보를
여러 장 동시 기동할 때 전원이 부족하면 보드가 리셋되니, 외부 5~6V 전원을 PCA9685
V+ 에 공급하고 아두이노와 공통 접지하세요.

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

