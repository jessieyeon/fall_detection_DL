"""인증 라우트와 세션 헬퍼."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from webservice import auth, db

router = APIRouter(prefix="/api/auth")


class LoginBody(BaseModel):
    email: str
    password: str


def _public(row):
    return {"id": row["id"], "email": row["email"],
            "role": row["role"], "name": row["name"],
            "facility_name": row["facility_name"]}


def current_user(request: Request):
    user = request.session.get("user")
    if user is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    return user


@router.post("/login")
def login(body: LoginBody, request: Request):
    conn = db.connect()
    try:
        row = auth.authenticate(conn, body.email, body.password)
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 틀렸습니다")
    user = _public(row)
    request.session["user"] = user
    return user


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"status": "ok"}


@router.get("/me")
def me(request: Request):
    return current_user(request)
