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


def with_device(message, device):
    """이벤트에 카메라 표시를 붙인다. 브라우저는 보고 있는 카메라 것만 그린다.

    device 가 비어 있으면(익명 파이프라인) 키를 넣지 않는다 — 예전 형식 그대로라
    구버전 프런트도 계속 동작한다.
    """
    if device:
        return {**message, "device": device}
    return message


def fall_message(tiles, rows, cols, direction):
    """낙상 판정 결과.

    이 메시지는 완충 타일이 실제로 전개됐을 때만 나간다(main.py 가 ack 를 확인한다).
    화면의 붉은 타일은 곧 '하드웨어가 움직였다'는 뜻이고, 그래서 화면과 실물이
    어긋나지 않는다.
    """
    return {"type": "fall", "tiles": [int(t) for t in tiles],
            "rows": int(rows), "cols": int(cols),
            "direction": round(float(direction), 1)}


def reset_message():
    return {"type": "reset"}


# device_key 를 안 붙이고 띄우는 파이프라인(기존 실행 방식)이 들어갈 자리.
# 익명 카메라도 한 대짜리 스트림으로는 정상 동작해야 한다.
DEFAULT_DEVICE = ""


class FrameStore:
    """카메라별로 가장 최근 프레임(JPEG 바이트) 한 장씩 들고 있는다.

    스켈레톤 좌표만 보내면 브라우저에는 검은 배경 위의 선만 그려져서, 카메라가
    실제로 무엇을 보고 있는지 알 수 없다. 영상까지 보여야 '연결됐다'는 감각이
    생기고 오검출 원인도 눈으로 확인할 수 있다.

    큐가 아니라 한 장만 유지하는 이유: 실시간 화면에서는 늦은 프레임이 쓸모없다.
    소비자가 느리면 밀린 프레임을 쌓는 대신 최신 것만 보여주는 게 맞다.

    카메라별로 나눠 담는 이유: 예전에는 전역으로 한 장만 들고 있어서 파이프라인을
    두 개 띄우면 서로 프레임을 덮어썼다. 실버타운처럼 여러 공간을 동시에 보는
    설치에서는 성립하지 않는다.
    """

    def __init__(self):
        self._frames = {}       # device_key -> (seq, jpeg)
        self._seq = 0           # 전역 카운터 — 전체 수신량 지표로도 쓴다

    def put(self, jpeg_bytes, device=DEFAULT_DEVICE):
        self._seq += 1
        self._frames[device] = (self._seq, jpeg_bytes)
        return self._seq

    def get(self, device=DEFAULT_DEVICE):
        """(시퀀스 번호, JPEG 바이트). 아직 없으면 (0, None)."""
        return self._frames.get(device, (0, None))

    def devices(self):
        """프레임이 한 번이라도 들어온 카메라 목록."""
        return sorted(self._frames)

    @property
    def seq(self):
        return self._seq


class CameraControl:
    """브라우저 → 감지 파이프라인 제어 신호. 카메라별로 따로 기억한다.

    브라우저는 서버에만 말할 수 있고, 카메라를 쥐고 있는 것은 사용자 PC 에서 도는
    main.py 다. 그래서 서버가 '멈춰달라'는 요청을 들고 있다가, 파이프라인이 주기적으로
    물어보면 알려주는 방식으로 잇는다.

    화면만 가리는 것과 다르다. 파이프라인이 이 신호를 보면 `cv2.VideoCapture` 를
    실제로 놓아주므로 카메라 장치가 해제된다(아이폰 연속성 카메라라면 폰에서도
    사용 중 표시가 사라진다).

    전역 플래그 하나였을 때는 카메라 한 대를 끊으면 전부 멈췄다.
    """

    def __init__(self):
        self._paused = {}       # device_key -> bool

    def paused_for(self, device=DEFAULT_DEVICE):
        return self._paused.get(device, False)

    def set_paused(self, value, device=DEFAULT_DEVICE):
        self._paused[device] = bool(value)
        return self._paused[device]

    @property
    def paused(self):
        """기본(익명) 카메라의 상태. 단일 카메라 호출부 호환용."""
        return self.paused_for()


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
