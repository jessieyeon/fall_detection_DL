"""실시간 중계: 와이어 메시지 빌더 + WebSocket 브로드캐스트 허브.

메시지 형식은 기존 webapp_server.py 와 동일하게 유지해 main.py 파이프라인이
그대로 붙을 수 있게 한다.
"""


def pose_message(landmarks, shape, risk, consec, persistence):
    if landmarks is None:
        pts = None
    else:
        h, w = shape[0], shape[1]
        pts = [[round(x / w, 4), round(y / h, 4)] for (x, y, *_rest) in landmarks]
    return {"type": "pose", "landmarks": pts,
            "risk": round(float(risk), 3),
            "prog": [int(consec), int(persistence)]}


def fall_message(tiles, rows, cols, direction):
    return {"type": "fall", "tiles": [int(t) for t in tiles],
            "rows": int(rows), "cols": int(cols),
            "direction": round(float(direction), 1)}


def reset_message():
    return {"type": "reset"}


class ConnectionManager:
    """구독 중인 WebSocket 집합. ponytail: 인메모리·단일 프로세스 데모 한정."""

    def __init__(self):
        self._clients = set()

    async def connect(self, ws):
        self._clients.add(ws)

    def disconnect(self, ws):
        self._clients.discard(ws)

    async def broadcast(self, message):
        dead = []
        for ws in list(self._clients):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)
