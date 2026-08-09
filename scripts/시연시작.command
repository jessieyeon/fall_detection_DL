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

# 이 스크립트가 어디에 있든 저장소 루트에서 실행되게 한다. 더블클릭하면
# 작업 디렉터리가 홈이라, cd 없이는 main.py 를 못 찾는다.
cd "$(dirname "$0")/.." || exit 1

echo "다온 안전지킴이 — 시연 시작"
echo "  카메라 $CAMERA → $LIVE_URL"
echo "  (멈추려면 Control-C)"
echo

# --port 를 안 주면 아두이노 없이도 시뮬레이션 모드로 돌아간다. 즉 타일이
# 안 꽂혀 있어도 화면 시연은 그대로 된다.
exec python3 main.py "$CAMERA" \
  --live-url "$LIVE_URL" \
  --device-key "$DEVICE_KEY"
