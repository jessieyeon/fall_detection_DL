"""모바일 뷰어 앱을 위한 실시간 웹서버.

맥북에서 도는 파이썬 파이프라인(main.py)이 포즈 좌표와 낙상 이벤트를 이 서버로
밀어넣으면, 같은 WiFi 에 있는 폰 브라우저가 WebSocket 으로 받아 스켈레톤과
가상 2x2 타일을 그린다.

설계 요지:
  - 아두이노는 여전히 맥북 USB 에 물려 있고 실제 타일은 tile_protocol.py 가 움직인다.
    이 서버는 "무엇이 발사됐는지"를 앱에도 알려주는 브로드캐스트 채널일 뿐이다.
  - 영상 자체는 전송하지 않는다. 관절 좌표(작은 JSON)만 보내고 앱이 다시 그린다.
  - 낙상 감지 로직에는 전혀 관여하지 않는다. 서버가 죽어도 파이프라인은 돌아야 한다.

의존성(fastapi, uvicorn)은 --webapp 를 쓸 때만 필요하므로 start() 안에서 지연
임포트한다. 웹앱을 안 쓰는 사용자는 이 패키지를 설치하지 않아도 된다.
"""

import asyncio
import json
import os
import socket
import threading
import time


def _lan_ip():
    """이 컴퓨터의 LAN IP 를 추정한다. 실제로 패킷을 보내지는 않는다."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))   # 라우팅 테이블만 참조, 전송은 없음
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


class WebAppServer:
    def __init__(self, host="0.0.0.0", port=8000, static_dir=None):
        self.host = host
        self.port = port
        self.static_dir = static_dir or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "webapp")
        self._loop = None          # uvicorn 이벤트 루프 (다른 스레드에서 브로드캐스트할 때 필요)
        self._clients = set()
        self._thread = None
        self._server = None
        self._last_pose_sent = 0.0
        self.pose_min_interval = 1.0 / 20   # 포즈 메시지를 ~20fps 로 제한(폰 과부하 방지)

    # --- 기동 ---

    def start(self):
        """웹서버를 데몬 스레드에서 띄운다. 실패해도 예외를 던지지 않는다."""
        try:
            import uvicorn
            from fastapi import FastAPI, WebSocket
            from fastapi.responses import FileResponse, HTMLResponse
        except Exception as exc:
            print(f"[앱] 경고: fastapi/uvicorn 을 불러올 수 없습니다 ({exc}). "
                  "pip install fastapi 'uvicorn[standard]' 후 다시 시도하세요. "
                  "웹앱 없이 파이프라인만 계속 진행합니다.")
            return False

        app = FastAPI()
        index_path = os.path.join(self.static_dir, "index.html")

        @app.get("/")
        async def index():
            if os.path.isfile(index_path):
                return FileResponse(index_path)
            return HTMLResponse("<h1>webapp/index.html 이 없습니다.</h1>", status_code=404)

        @app.websocket("/ws")
        async def ws(websocket: WebSocket):
            await websocket.accept()
            self._clients.add(websocket)
            try:
                # 클라이언트는 보통 데이터를 안 보낸다. 연결 유지 및 종료 감지용.
                while True:
                    await websocket.receive_text()
            except Exception:
                pass
            finally:
                self._clients.discard(websocket)

        @app.on_event("startup")
        async def _capture_loop():
            # 브로드캐스트는 main 스레드(동기 루프)에서 호출되므로 이 루프 참조가 필요하다.
            self._loop = asyncio.get_running_loop()

        config = uvicorn.Config(app, host=self.host, port=self.port, log_level="warning")
        self._server = uvicorn.Server(config)
        # uvicorn 은 non-main 스레드에서는 시그널 핸들러 설치를 스스로 건너뛴다.
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        ip = _lan_ip()
        print("[앱] 웹서버 시작됨. 맥과 같은 WiFi 의 폰 브라우저에서 아래 주소를 여세요:")
        print(f"[앱]    ▶  http://{ip}:{self.port}")
        print(f"[앱]    (같은 맥에서 확인만 할 땐 http://localhost:{self.port})")
        return True

    # --- 브로드캐스트 (동기 main 스레드에서 호출) ---

    def _broadcast(self, message):
        if self._loop is None or not self._clients:
            return
        data = json.dumps(message, separators=(",", ":"))
        try:
            asyncio.run_coroutine_threadsafe(self._send_all(data), self._loop)
        except Exception:
            pass

    async def _send_all(self, data):
        dead = []
        for ws in list(self._clients):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)

    def push_pose(self, landmarks, shape, risk_score, consecutive, persistence):
        """관절 좌표를 화면 크기로 정규화(0~1)해 전송한다. 추적 상실이면 landmarks=None."""
        now = time.monotonic()
        if now - self._last_pose_sent < self.pose_min_interval:
            return
        self._last_pose_sent = now

        if landmarks is None:
            pts = None
        else:
            h, w = shape[0], shape[1]
            pts = [[round(x / w, 4), round(y / h, 4)] for (x, y, *_rest) in landmarks]

        self._broadcast({
            "type": "pose",
            "landmarks": pts,
            "risk": round(float(risk_score), 3),
            "prog": [int(consecutive), int(persistence)],
        })

    def push_fall(self, tiles, rows, cols, direction_deg):
        self._broadcast({
            "type": "fall",
            "tiles": [int(t) for t in tiles],
            "rows": int(rows),
            "cols": int(cols),
            "direction": round(float(direction_deg), 1),
        })

    def push_reset(self):
        self._broadcast({"type": "reset"})

    def stop(self):
        if self._server is not None:
            self._server.should_exit = True
