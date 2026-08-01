"""다온 웹 서비스 FastAPI 진입점."""

import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from webservice import db
from webservice.routes_auth import router as auth_router
from webservice.routes_survey import router as survey_router
from webservice.routes_guardian import router as guardian_router
from webservice.routes_home import router as home_router
from webservice.routes_consulting import router as consulting_router
from webservice.routes_live import router as live_router

app = FastAPI(title="다온 낙상 케어")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("DAON_SECRET", "dev-demo-secret-change-me"),
)
app.include_router(auth_router)
app.include_router(survey_router)
app.include_router(guardian_router)
app.include_router(home_router)
app.include_router(consulting_router)
app.include_router(live_router)


@app.on_event("startup")
def _startup():
    db.init_db()


@app.get("/api/health")
def health():
    return {"status": "ok"}


# 빌드된 React SPA 를 같은 서버에서 서빙한다(단일 서버 시연). dist 가 없으면
# (빌드 전/테스트) 이 블록은 건너뛰므로 API 전용으로 동작한다.
_DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "dist")
if os.path.isdir(_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(_DIST, "assets")),
              name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        # /api·/ws 를 제외한 모든 경로는 index.html 로 돌려 클라이언트 라우팅을
        # 유지한다(/login, /mypage, /live 새로고침에도 안 깨지게).
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        return FileResponse(os.path.join(_DIST, "index.html"))
