"""다온 웹 서비스 FastAPI 진입점."""

from fastapi import FastAPI

from webservice import db

app = FastAPI(title="다온 낙상 케어")


@app.on_event("startup")
def _startup():
    db.init_db()


@app.get("/api/health")
def health():
    return {"status": "ok"}
