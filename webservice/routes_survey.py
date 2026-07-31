"""설문 문항 조회·제출·최신 결과 라우트."""

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from webservice import db, survey
from webservice.routes_auth import current_user

router = APIRouter(prefix="/api/survey")


class SubmitBody(BaseModel):
    answers: dict


@router.get("/questions")
def questions():
    return survey.load_questions()


@router.post("")
def submit(body: SubmitBody, user=Depends(current_user)):
    try:
        score, level = survey.score_answers(body.answers)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    conn = db.connect()
    try:
        conn.execute(
            "INSERT INTO surveys (user_id, answers_json, score, risk_level) "
            "VALUES (?, ?, ?, ?)",
            (user["id"], json.dumps(body.answers, ensure_ascii=False), score, level))
        conn.commit()
    finally:
        conn.close()
    return {"score": score, "risk_level": level}


@router.get("/latest")
def latest(user=Depends(current_user)):
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT score, risk_level, created_at FROM surveys "
            "WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user["id"],)).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None
