"""실시간 중계 라우트: 브라우저 WS 구독 + 파이프라인 이벤트 인제스트."""

import os

from fastapi import APIRouter, Header, HTTPException, WebSocket

from webservice import live

router = APIRouter()
manager = live.ConnectionManager()

_VALID_TYPES = {"pose", "fall", "reset"}


def _ingest_token():
    return os.environ.get("LIVE_INGEST_TOKEN", "daon-live")


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
    if x_live_token != _ingest_token():
        raise HTTPException(status_code=401, detail="invalid ingest token")
    if message.get("type") not in _VALID_TYPES:
        raise HTTPException(status_code=400, detail="unknown event type")
    await manager.broadcast(message)
    return {"delivered": len(manager._clients)}
