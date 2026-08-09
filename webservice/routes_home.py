"""근처 병원 조회 라우트.

낙상 알림에서 '119 신고 지원' 화면을 열 때, 시설 주소를 좌표로 바꿔 주변 병원을
함께 보여주는 데 쓴다. 아파트 평면도 매칭 기능이 여기 같이 있었으나 실버타운으로
무대를 옮기면서 제거했다(가정집 평면도가 시설 서사와 맞지 않고, 화면에서 호출한
적도 없다).
"""

from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from webservice import db, hospitals
from webservice.routes_auth import current_user

router = APIRouter(prefix="/api/home")


def _client_factory():
    # 테스트에서 MockTransport 클라이언트로 교체하는 지점.
    return httpx.Client(timeout=5)


@router.get("/hospitals")
def nearby(user=Depends(current_user),
           lat: Optional[float] = Query(None), lng: Optional[float] = Query(None)):
    # lat/lng 를 주면(브라우저 GPS) 그 좌표로, 아니면 등록된 주소로 병원을 찾는다.
    client = _client_factory()
    try:
        if lat is not None and lng is not None:
            coords = (lng, lat)
        else:
            conn = db.connect()
            try:
                row = conn.execute("SELECT address FROM users WHERE id = ?",
                                   (user["id"],)).fetchone()
            finally:
                conn.close()
            address = row["address"] if row else ""
            if not address:
                raise HTTPException(status_code=400, detail="주소가 등록되어 있지 않습니다")
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
