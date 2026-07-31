"""평면도 매칭과 근처 병원 라우트."""

import json
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from webservice import db, hospitals
from webservice.routes_auth import current_user

router = APIRouter(prefix="/api/home")

_FLOORPLAN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "data", "floorplans")


def _client_factory():
    # 테스트에서 MockTransport 클라이언트로 교체하는 지점.
    return httpx.Client(timeout=5)


def _manifest():
    with open(os.path.join(_FLOORPLAN_DIR, "manifest.json"), encoding="utf-8") as f:
        return json.load(f)


@router.get("/floorplan")
def floorplan(apartment: str = Query(...)):
    filename = _manifest().get(apartment)
    if not filename:
        raise HTTPException(status_code=404, detail="평면도를 찾을 수 없습니다")
    return FileResponse(os.path.join(_FLOORPLAN_DIR, filename))


@router.get("/hospitals")
def nearby(user=Depends(current_user)):
    conn = db.connect()
    try:
        row = conn.execute("SELECT address FROM users WHERE id = ?",
                           (user["id"],)).fetchone()
    finally:
        conn.close()
    address = row["address"] if row else ""
    if not address:
        raise HTTPException(status_code=400, detail="주소가 등록되어 있지 않습니다")
    client = _client_factory()
    try:
        coords = hospitals.geocode(address, client=client)
        if coords is None:
            raise HTTPException(status_code=404, detail="주소를 좌표로 변환하지 못했습니다")
        return hospitals.nearby_hospitals(coords[0], coords[1], client=client)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except httpx.HTTPStatusError:
        raise HTTPException(status_code=502, detail="병원 정보를 불러오지 못했습니다")
    finally:
        client.close()
