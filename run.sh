#!/usr/bin/env bash
# 앱(웹 플랫폼) + 감지 파이프라인 + 아두이노를 한 번에 실행한다.
#
# 사용법:
#   ./run.sh                     웹캠 + 자동 탐지한 아두이노 포트
#   PORT=/dev/cu.xxx ./run.sh    포트를 직접 지정
#   SOURCE=test_videos/a.mp4 ./run.sh   웹캠 대신 녹화 영상
#
# 아두이노 포트는 자동 탐지(macOS: /dev/cu.usbmodem*, Linux: /dev/ttyACM*).
# 못 찾으면 서보 없이(시뮬레이션) 계속 진행한다. Ctrl-C 로 둘 다 종료.
set -eo pipefail
cd "$(dirname "$0")"

PLATFORM_URL="http://localhost:8000"

if [ ! -d webservice/frontend/dist ]; then
  echo "[run] 경고: 프런트가 빌드 안 됨 → 화면이 비어 보임."
  echo "      먼저: (cd webservice/frontend && npm install && npm run build)"
fi

# 1) 웹 플랫폼(uvicorn) 백그라운드 실행
echo "[run] 웹 플랫폼 시작: $PLATFORM_URL"
python3 -m uvicorn webservice.app:app --port 8000 --log-level warning &
UVICORN_PID=$!
# Ctrl-C 나 어떤 이유로 스크립트가 끝나도 백그라운드 서버를 반드시 같이 정리한다.
trap 'echo; echo "[run] 종료 중..."; kill $UVICORN_PID 2>/dev/null || true' EXIT

# 2) 서버가 응답할 때까지 대기(최대 ~20초)
for _ in $(seq 1 40); do
  if curl -sf -o /dev/null "$PLATFORM_URL"; then break; fi
  sleep 0.5
done
echo "[run] 준비됨 → 브라우저에서 $PLATFORM_URL 접속"

# 3) 아두이노 포트: PORT 환경변수 우선, 없으면 자동 탐지
PORT="${PORT:-$(ls /dev/cu.usbmodem* /dev/ttyACM* 2>/dev/null | head -n1 || true)}"
PORT_ARG=()
if [ -n "$PORT" ]; then
  echo "[run] 아두이노 포트: $PORT"
  PORT_ARG=(--port "$PORT")
else
  echo "[run] 아두이노 포트 못 찾음 → 서보 없이(시뮬레이션) 진행"
fi

# 4) 감지 파이프라인(포그라운드). 여기서 Ctrl-C 하면 위 trap 이 서버까지 정리한다.
python3 main.py "${SOURCE:-0}" "${PORT_ARG[@]}" --live-url "$PLATFORM_URL"
