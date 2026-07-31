"""다온 웹 서비스 FastAPI 진입점."""

import os

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from webservice import db
from webservice.routes_auth import router as auth_router
from webservice.routes_survey import router as survey_router
from webservice.routes_guardian import router as guardian_router

app = FastAPI(title="다온 낙상 케어")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("DAON_SECRET", "dev-demo-secret-change-me"),
)
app.include_router(auth_router)
app.include_router(survey_router)
app.include_router(guardian_router)


@app.on_event("startup")
def _startup():
    db.init_db()


@app.get("/api/health")
def health():
    return {"status": "ok"}
