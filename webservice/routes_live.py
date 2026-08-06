"""실시간 중계 라우트: 브라우저 WS 구독 + 파이프라인 이벤트·프레임 인제스트."""

import asyncio
import os

from fastapi import APIRouter, Header, HTTPException, Request, Response, WebSocket
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from webservice import live

router = APIRouter()
manager = live.ConnectionManager()
frames = live.FrameStore()
control = live.CameraControl()

_VALID_TYPES = {"pose", "fall", "reset"}
_REQUIRED = {"pose": ("landmarks",), "fall": ("tiles", "rows", "cols"), "reset": ()}

# 프레임이 이 시간 이상 안 들어오면 파이프라인이 끊긴 것으로 보고 스트림을 닫는다.
STREAM_IDLE_TIMEOUT = 10.0
MAX_FRAME_BYTES = 2 * 1024 * 1024


def _ingest_token():
    return os.environ.get("LIVE_INGEST_TOKEN", "daon-live")


def _check_token(token):
    if token != _ingest_token():
        raise HTTPException(status_code=401, detail="invalid ingest token")


@router.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    # 세션 쿠키로 로그인한 브라우저만 스켈레톤 스트림을 볼 수 있다.
    if websocket.session.get("user") is None:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()      # 클라이언트는 보통 안 보냄; 종료 감지용
    except Exception:
        pass
    finally:
        manager.disconnect(websocket)


@router.post("/api/live/event")
async def live_event(message: dict, x_live_token: str = Header(default="")):
    _check_token(x_live_token)
    if message.get("type") not in _VALID_TYPES:
        raise HTTPException(status_code=400, detail="unknown event type")
    missing = [k for k in _REQUIRED[message["type"]] if k not in message]
    if missing:
        raise HTTPException(status_code=400, detail=f"missing fields: {missing}")
    await manager.broadcast(message)
    return {"delivered": len(manager._clients)}


@router.post("/api/live/frame")
async def live_frame(request: Request, x_live_token: str = Header(default="")):
    """파이프라인이 보내는 카메라 프레임(JPEG). 최신 한 장만 보관한다."""
    _check_token(x_live_token)
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="empty frame")
    if len(body) > MAX_FRAME_BYTES:
        raise HTTPException(status_code=413, detail="frame too large")
    frames.put(body)
    return {"ok": True, "seq": frames.seq}


@router.get("/api/live/frame.jpg")
def latest_frame():
    """가장 최근 프레임 한 장. MJPEG 가 막히는 환경을 위한 폴백."""
    _seq, jpeg = frames.get()
    if jpeg is None:
        raise HTTPException(status_code=404, detail="아직 들어온 프레임이 없습니다")
    return Response(content=jpeg, media_type="image/jpeg",
                    headers={"Cache-Control": "no-store"})


@router.get("/api/live/stream.mjpg")
async def stream():
    """MJPEG 스트림. `<img src="...">` 에 그대로 꽂으면 영상이 재생된다.

    프레임마다 새 요청을 보내는 폴링과 달리 연결 하나로 계속 흘려보내므로
    지연이 적고 요청 수도 줄어든다. 새 프레임이 들어왔을 때만 내보내서,
    파이프라인이 20fps 면 같은 그림을 반복 전송하지 않는다.
    """
    boundary = "daonframe"

    async def gen():
        last_seq = -1
        idle = 0.0
        while True:
            seq, jpeg = frames.get()
            if jpeg is not None and seq != last_seq:
                last_seq = seq
                idle = 0.0
                yield (f"--{boundary}\r\nContent-Type: image/jpeg\r\n"
                       f"Content-Length: {len(jpeg)}\r\n\r\n").encode()
                yield jpeg
                yield b"\r\n"
            else:
                idle += 0.04
                if idle > STREAM_IDLE_TIMEOUT:
                    return          # 파이프라인이 끊겼다 — 연결을 붙잡고 있지 않는다
            await asyncio.sleep(0.04)

    return StreamingResponse(
        gen(),
        media_type=f"multipart/x-mixed-replace; boundary={boundary}",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/api/live/status")
def status():
    """파이프라인이 붙어 있는지. 프런트가 카메라 연결 여부를 판단할 때 쓴다."""
    return {"frames": frames.seq, "viewers": len(manager._clients),
            "paused": control.paused}


class PauseBody(BaseModel):
    paused: bool


@router.post("/api/live/control")
def set_control(body: PauseBody, request: Request):
    """브라우저에서 카메라를 잠시 끊거나 다시 연결한다.

    로그인한 사용자만 조작할 수 있다. 실제로 카메라를 놓는 것은 파이프라인이므로,
    여기서는 요청만 기록하고 파이프라인이 가져가기를 기다린다.
    """
    if request.session.get("user") is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    return {"paused": control.set_paused(body.paused)}


@router.get("/api/live/control")
def get_control(x_live_token: str = Header(default="")):
    """파이프라인이 주기적으로 물어보는 지점."""
    _check_token(x_live_token)
    return {"paused": control.paused}
