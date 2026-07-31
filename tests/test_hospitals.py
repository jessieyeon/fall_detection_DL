import json
import httpx
import pytest
from webservice import hospitals


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_geocode_returns_lng_lat(monkeypatch):
    monkeypatch.setenv("KAKAO_REST_KEY", "test-key")

    def handler(request):
        assert "search/address.json" in str(request.url)
        assert request.headers["Authorization"] == "KakaoAK test-key"
        return httpx.Response(200, json={"documents": [{"x": "127.1", "y": "37.5"}]})

    assert hospitals.geocode("서울시 어딘가", client=_client(handler)) == (127.1, 37.5)


def test_geocode_no_result_is_none(monkeypatch):
    monkeypatch.setenv("KAKAO_REST_KEY", "k")
    handler = lambda request: httpx.Response(200, json={"documents": []})
    assert hospitals.geocode("없는주소", client=_client(handler)) is None


def test_nearby_hospitals_maps_fields(monkeypatch):
    monkeypatch.setenv("KAKAO_REST_KEY", "k")

    def handler(request):
        assert "search/category.json" in str(request.url)
        assert "HP8" in str(request.url)
        return httpx.Response(200, json={"documents": [
            {"place_name": "다온병원", "road_address_name": "도로명 1",
             "address_name": "지번 1", "phone": "02-000", "distance": "150",
             "place_url": "http://x"}]})

    out = hospitals.nearby_hospitals(127.1, 37.5, client=_client(handler))
    assert out == [{"name": "다온병원", "address": "도로명 1", "phone": "02-000",
                    "distance_m": 150, "url": "http://x"}]


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("KAKAO_REST_KEY", raising=False)
    with pytest.raises(RuntimeError):
        hospitals.geocode("x", client=_client(lambda r: httpx.Response(200, json={})))
