"""카카오 로컬 API 래퍼 — 주소 지오코딩과 근처 병원 검색.

KAKAO_REST_KEY 환경변수 필요. client 인자는 테스트에서 httpx.MockTransport 주입용.
"""

import os

import httpx

_BASE = "https://dapi.kakao.com/v2/local"


def _headers():
    key = os.environ.get("KAKAO_REST_KEY")
    if not key:
        raise RuntimeError("KAKAO_REST_KEY 환경변수가 설정되지 않았습니다")
    return {"Authorization": f"KakaoAK {key}"}


def _get(client, path, params):
    own = client is None
    c = client or httpx.Client(timeout=5)
    try:
        r = c.get(f"{_BASE}/{path}", headers=_headers(), params=params)
        r.raise_for_status()
        return r.json()
    finally:
        if own:
            c.close()


def geocode(address, client=None):
    docs = _get(client, "search/address.json", {"query": address}).get("documents", [])
    if not docs:
        return None
    return float(docs[0]["x"]), float(docs[0]["y"])


def nearby_hospitals(lng, lat, radius=2000, client=None):
    data = _get(client, "search/category.json", {
        "category_group_code": "HP8", "x": lng, "y": lat,
        "radius": radius, "sort": "distance"})
    return [{
        "name": d["place_name"],
        "address": d.get("road_address_name") or d.get("address_name", ""),
        "phone": d.get("phone", ""),
        "distance_m": int(d.get("distance") or 0),
        "url": d.get("place_url", ""),
    } for d in data.get("documents", [])]
