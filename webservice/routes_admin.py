"""관리자 라우트 — 시설 정보, 입주민, 카메라.

routes_guardian.py(보호자-어르신 페어링)를 대체한다. 역할이 admin 하나뿐이므로
역할 검사는 없고, 로그인 여부와 '내 데이터인지'만 본다.
"""

import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from webservice import cameras, db
from webservice.routes_auth import current_user

router = APIRouter(prefix="/api/admin")


def _integrity(exc):
    """sqlite IntegrityError 를 사람이 읽을 수 있는 400 으로 바꾼다.

    그대로 두면 FastAPI 가 500 을 내고 프런트에는 'Internal Server Error' 만
    뜬다. 실제로 '어르신 추가가 안 돼요'라는 제보의 원인이 화면에서는 전혀
    보이지 않았다.
    """
    if "FOREIGN KEY" in str(exc):
        return HTTPException(
            status_code=401,
            detail="로그인 정보가 만료되었습니다. 다시 로그인한 뒤 시도해 주세요.")
    return HTTPException(status_code=400, detail=f"저장하지 못했습니다: {exc}")

# 프런트가 설치 공간 선택지를 하드코딩하지 않도록 서버가 알려준다.
# 공간 이름이 또 바뀔 때 두 곳을 고치다 한 곳을 빠뜨리는 일을 막는다.
_UNSET = object()


class FacilityBody(BaseModel):
    facility_name: Optional[str] = None
    address: Optional[str] = None


class ResidentBody(BaseModel):
    name: str
    age: Optional[int] = None
    room: str = ""
    phone: str = ""
    note: str = ""
    address: str = ""          # 개별 주소(선택). 있으면 신고 지원이 이걸 쓴다
    address_detail: str = ""   # 상세 주소(동·호수 등). 주소 검색으로는 안 나온다


class ResidentPatch(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    room: Optional[str] = None
    phone: Optional[str] = None
    note: Optional[str] = None
    address: Optional[str] = None
    address_detail: Optional[str] = None


class CameraBody(BaseModel):
    device_key: str
    name: str
    location: str
    resident_id: Optional[int] = None


class CameraPatch(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    # 미지정과 '연결 해제(null)'를 구분하려고 문자열 sentinel 을 쓴다.
    resident_id: Optional[int] = None
    clear_resident: bool = False


def _conn():
    return db.connect()


@router.get("/meta")
def meta(user=Depends(current_user)):
    """프런트가 쓰는 상수. 설치 공간 목록이 서버 것과 어긋나지 않게 한다."""
    return {"locations": list(db.LOCATIONS)}


# ── 시설 정보 ─────────────────────────────────────────────────────────

@router.get("/facility")
def get_facility(user=Depends(current_user)):
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT name, facility_name, address FROM users WHERE id = ?",
            (user["id"],)).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


@router.patch("/facility")
def set_facility(body: FacilityBody, user=Depends(current_user)):
    sets, vals = [], []
    if body.facility_name is not None:
        sets.append("facility_name = ?"); vals.append(body.facility_name.strip())
    if body.address is not None:
        sets.append("address = ?"); vals.append(body.address.strip())
    if not sets:
        return {"updated": False}
    vals.append(user["id"])
    conn = _conn()
    try:
        conn.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = ?", vals)
        conn.commit()
    finally:
        conn.close()
    return {"updated": True}


# ── 입주민 ────────────────────────────────────────────────────────────

@router.get("/residents")
def get_residents(user=Depends(current_user)):
    conn = _conn()
    try:
        return cameras.list_residents(conn, user["id"])
    finally:
        conn.close()


@router.post("/residents")
def post_resident(body: ResidentBody, user=Depends(current_user)):
    conn = _conn()
    try:
        rid = cameras.create_resident(
            conn, user["id"], body.name, body.age, body.room, body.phone,
            body.note, body.address, body.address_detail)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except sqlite3.IntegrityError as exc:
        raise _integrity(exc)
    finally:
        conn.close()
    return {"id": rid}


@router.patch("/residents/{resident_id}")
def patch_resident(resident_id: int, body: ResidentPatch, user=Depends(current_user)):
    conn = _conn()
    try:
        ok = cameras.update_resident(conn, user["id"], resident_id,
                                     **body.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        conn.close()
    if not ok:
        raise HTTPException(status_code=404, detail="입주민을 찾을 수 없습니다")
    return {"updated": True}


@router.delete("/residents/{resident_id}")
def remove_resident(resident_id: int, user=Depends(current_user)):
    conn = _conn()
    try:
        ok = cameras.delete_resident(conn, user["id"], resident_id)
    finally:
        conn.close()
    if not ok:
        raise HTTPException(status_code=404, detail="입주민을 찾을 수 없습니다")
    return {"deleted": True}


# ── 카메라 ────────────────────────────────────────────────────────────

@router.get("/cameras")
def get_cameras(user=Depends(current_user)):
    conn = _conn()
    try:
        return cameras.list_cameras(conn, user["id"])
    finally:
        conn.close()


@router.get("/cameras/scan")
def scan(user=Depends(current_user)):
    """'주변 카메라 찾기' — 신호는 왔는데 아직 등록되지 않은 기기."""
    conn = _conn()
    try:
        return cameras.discoverable(conn, user["id"])
    finally:
        conn.close()


@router.post("/cameras")
def post_camera(body: CameraBody, user=Depends(current_user)):
    conn = _conn()
    try:
        cid = cameras.register_camera(conn, user["id"], body.device_key,
                                      body.name, body.location, body.resident_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except sqlite3.IntegrityError as exc:
        raise _integrity(exc)
    finally:
        conn.close()
    return {"id": cid}


@router.patch("/cameras/{camera_id}")
def patch_camera(camera_id: int, body: CameraPatch, user=Depends(current_user)):
    resident = None if body.clear_resident else (
        body.resident_id if body.resident_id is not None else ...)
    conn = _conn()
    try:
        ok = cameras.update_camera(conn, user["id"], camera_id,
                                   name=body.name, location=body.location,
                                   resident_id=resident)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        conn.close()
    if not ok:
        raise HTTPException(status_code=404, detail="카메라를 찾을 수 없습니다")
    return {"updated": True}


@router.delete("/cameras/{camera_id}")
def remove_camera(camera_id: int, user=Depends(current_user)):
    conn = _conn()
    try:
        ok = cameras.delete_camera(conn, user["id"], camera_id)
    finally:
        conn.close()
    if not ok:
        raise HTTPException(status_code=404, detail="카메라를 찾을 수 없습니다")
    return {"deleted": True}


@router.get("/cameras/{camera_id}/dispatch")
def dispatch(camera_id: int, user=Depends(current_user)):
    """119 신고 지원 정보. 자동 신고가 아니라 관리자가 읽을 내용을 만든다."""
    conn = _conn()
    try:
        info = cameras.dispatch_info(conn, camera_id)
    finally:
        conn.close()
    if info is None:
        raise HTTPException(status_code=404, detail="카메라를 찾을 수 없습니다")
    return info
