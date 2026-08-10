#!/bin/bash
# 전시 시연 실행기 — 터미널에 명령을 치지 않으려고 둔다. 파인더에서 더블클릭.
#
# 하는 일: iPhone(연속성 카메라)을 웹캠으로 읽어 낙상을 판정하고, 그 결과를
#          배포 서버로 올린다. 아두이노가 꽂혀 있으면 타일까지 실제로 펴진다.
#
# 바꿔야 할 때:
#   CAMERA   카메라 인덱스. 내장 웹캠과 iPhone 중 어느 쪽인지는 아래 '확인' 참고
#   LIVE_URL 배포 주소. 로컬로 테스트하려면 http://localhost:8000
#
# 카메라 인덱스 확인:
#   python3 - <<'PY'
#   import cv2
#   for i in range(4):
#       cap = cv2.VideoCapture(i)
#       if cap.isOpened():
#           ok, f = cap.read()
#           if ok: cv2.imwrite(f"cam{i}.jpg", f); print(i, f.shape)
#           cap.release()
#   PY

# 0 = Mac 내장 웹캠. iPhone(연속성 카메라)은 OpenCV 가 목록에서 보지 못한다 —
# macOS 14 부터 연속성 카메라는 앱이 명시적으로 요청해야 나오는데 OpenCV 는
# 옛 방식으로 훑기 때문이다. iPhone 을 쓰려면 OBS 가상 카메라를 거친 뒤
# 그 인덱스로 바꾼다.
CAMERA=0
LIVE_URL="https://falldetectiondl-production.up.railway.app"
DEVICE_KEY="daon-cam-lounge-1"

# 전시장에서는 'demo' 프로파일을 쓴다. 기본값인 'human' 은 감지율을 최대로
# 잡아둔 평가용 동작점이라, 가만히 서 있어도 몇십 초에 한 번씩 타일이 튄다.
# 관람객 앞에서는 놓치는 것보다 헛발동이 더 나쁘다. 감도를 되돌리려면 human.
PROFILE=demo

# 이 스크립트가 어디에 있든 저장소 루트에서 실행되게 한다. 더블클릭하면
# 작업 디렉터리가 홈이라, cd 없이는 main.py 를 못 찾는다.
cd "$(dirname "$0")/.." || exit 1

# 아두이노 시리얼 포트를 자동으로 찾는다. 포트 이름(/dev/cu.usbmodem1101 등)은
# USB 포트를 바꿔 꽂거나 보드를 다시 연결할 때마다 뒷자리가 바뀌므로, 스크립트에
# 박아두면 전시장에서 반드시 한 번은 틀린다.
#   cu.* 를 쓰는 이유: tty.* 는 열 때 DCD(캐리어)를 기다려 아두이노에서 멈춘다.
# 포트를 못 찾으면 --port 를 아예 넘기지 않는다 → 시뮬레이션 모드로 화면 시연은
# 그대로 되고, 타일만 안 움직인다.
PORT=$(ls /dev/cu.usbmodem* /dev/cu.usbserial* /dev/cu.wchusbserial* 2>/dev/null | head -1)

echo "다온 안전지킴이 — 시연 시작"
echo "  카메라 $CAMERA → $LIVE_URL"
echo "  프로파일 $PROFILE"
if [ -n "$PORT" ]; then
  echo "  아두이노 $PORT"
else
  echo "  아두이노 없음 → 시뮬레이션 (화면은 정상, 타일만 안 움직임)"
fi
echo "  (멈추려면 Control-C)"
echo

if [ -n "$PORT" ]; then
  exec python3 main.py "$CAMERA" \
    --live-url "$LIVE_URL" \
    --device-key "$DEVICE_KEY" \
    --profile "$PROFILE" \
    --port "$PORT"
else
  exec python3 main.py "$CAMERA" \
    --live-url "$LIVE_URL" \
    --device-key "$DEVICE_KEY" \
    --profile "$PROFILE"
fi
