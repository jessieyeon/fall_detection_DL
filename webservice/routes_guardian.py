"""보호자 매칭(6자리 코드)과 상호 열람 라우트."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from webservice import db, pairing
from webservice.routes_auth import current_user

router = APIRouter(prefix="/api/guardian")


def _require(user, role):
    if user["role"] != role:
        raise HTTPException(status_code=403, detail=f"{role} 계정만 사용할 수 있습니다")


class RedeemBody(BaseModel):
    code: str


@router.post("/code")
def make_code(user=Depends(current_user)):
    _require(user, "senior")
    conn = db.connect()
    try:
        return {"code": pairing.generate_code(conn, user["id"])}
    finally:
        conn.close()


@router.post("/redeem")
def redeem(body: RedeemBody, user=Depends(current_user)):
    _require(user, "guardian")
    conn = db.connect()
    try:
        try:
            senior_id = pairing.redeem_code(conn, body.code, user["id"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        row = conn.execute("SELECT id, name FROM users WHERE id = ?",
                           (senior_id,)).fetchone()
        return {"senior": {"id": row["id"], "name": row["name"]}}
    finally:
        conn.close()


@router.get("/wards")
def wards(user=Depends(current_user)):
    _require(user, "guardian")
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT u.id, u.name, "
            "  (SELECT risk_level FROM surveys s WHERE s.user_id = u.id "
            "   ORDER BY s.id DESC LIMIT 1) AS risk_level "
            "FROM guardian_links gl JOIN users u ON u.id = gl.senior_id "
            "WHERE gl.guardian_id = ?", (user["id"],)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/list")
def guardian_list(user=Depends(current_user)):
    _require(user, "senior")
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT u.id, u.name FROM guardian_links gl "
            "JOIN users u ON u.id = gl.guardian_id WHERE gl.senior_id = ?",
            (user["id"],)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
