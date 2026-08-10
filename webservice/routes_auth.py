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
    """로그인한 사용자. **세션 값을 그대로 믿지 않고 DB 와 대조한다.**

    세션은 서명된 쿠키에 통째로 들어 있고 서버에 상태가 없다. 그래서 DB 가
    새로 만들어져도(컨테이너 재시작·재배포로 daon.db 가 날아가는 배포 환경이
    그렇다) 쿠키는 그대로 유효하다. 그러면 로그인은 되어 있는 것처럼 보이는데
    그 안의 id 는 users 에 없는 번호가 되고, 쓰기가 전부

        sqlite3.IntegrityError: FOREIGN KEY constraint failed

    로 죽는다 — 리포트 저장·어르신 추가·카메라 등록이 한꺼번에 실패한 원인이
    이것이다. 읽기는 빈 목록을 돌려주므로 증상이 '쓰기만 안 됨'으로 나타나
    더 헷갈렸다.

    그래서 매 요청에서 id 로 한 줄 읽는다(인덱스 조회라 비용은 무시할 만하다).
    id 가 사라졌으면 같은 이메일로 다시 만들어진 계정을 찾아 세션을 갱신하고
    (시드는 멱등이라 재배포마다 같은 이메일로 되살아난다), 그것도 없으면
    세션을 비우고 401 을 내 로그인 화면으로 돌려보낸다.
    """
    user = request.session.get("user")
    if user is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")

    conn = db.connect()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?",
                           (user.get("id"),)).fetchone()
        if row is None and user.get("email"):
            row = conn.execute("SELECT * FROM users WHERE email = ?",
                               (user["email"],)).fetchone()
    finally:
        conn.close()

    if row is None:
        request.session.clear()
        raise HTTPException(status_code=401,
                            detail="세션이 만료되었습니다. 다시 로그인해 주세요")

    fresh = _public(row)
    if fresh != user:
        request.session["user"] = fresh      # id·이름·시설명 변경분을 반영
    return fresh


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
