import httpx
from fastapi import HTTPException

from app.config import settings

_KAKAO_GEOCODE_URL = "https://dapi.kakao.com/v2/local/search/address.json"


async def geocode(address: str) -> tuple[float, float]:
    if not settings.kakao_rest_api_key:
        raise HTTPException(status_code=503, detail="geocoding_not_configured")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                _KAKAO_GEOCODE_URL,
                headers={"Authorization": f"KakaoAK {settings.kakao_rest_api_key}"},
                params={"query": address},
            )
        response.raise_for_status()
    except httpx.HTTPStatusError:
        raise HTTPException(status_code=502, detail="geocoding_upstream_error")
    except httpx.RequestError:
        raise HTTPException(status_code=502, detail="geocoding_upstream_error")

    documents = response.json().get("documents", [])
    if not documents:
        raise HTTPException(status_code=422, detail="address_not_found")

    # 카카오 API: x = 경도(longitude), y = 위도(latitude)
    first = documents[0]
    return float(first["y"]), float(first["x"])
