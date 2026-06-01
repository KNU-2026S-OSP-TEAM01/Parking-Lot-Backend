from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.kakao import geocode


def _make_response(documents: list, status_code: int = 200) -> MagicMock:
    mock = MagicMock(spec=httpx.Response)
    mock.status_code = status_code
    mock.json.return_value = {"documents": documents}
    if status_code >= 400:
        mock.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=mock
        )
    else:
        mock.raise_for_status.return_value = None
    return mock


SAMPLE_DOCUMENT = {
    "address_name": "전북 익산시 부송동 100",
    "y": "35.97664845766847",
    "x": "126.99597295767953",
    "address_type": "REGION_ADDR",
}


@pytest.mark.asyncio
async def test_geocode_success():
    mock_response = _make_response([SAMPLE_DOCUMENT])
    with patch("app.services.kakao.settings") as mock_settings, \
         patch("app.services.kakao.httpx.AsyncClient") as mock_client_cls:
        mock_settings.kakao_rest_api_key = "test-key"
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        lat, lng = await geocode("전북 삼성동 100")

    assert lat == pytest.approx(35.97664845766847)
    assert lng == pytest.approx(126.99597295767953)


@pytest.mark.asyncio
async def test_geocode_address_not_found():
    mock_response = _make_response([])
    with patch("app.services.kakao.settings") as mock_settings, \
         patch("app.services.kakao.httpx.AsyncClient") as mock_client_cls:
        mock_settings.kakao_rest_api_key = "test-key"
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with pytest.raises(Exception) as exc_info:
            await geocode("존재하지않는주소12345")

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "address_not_found"


@pytest.mark.asyncio
async def test_geocode_upstream_http_error():
    mock_response = _make_response([], status_code=401)
    with patch("app.services.kakao.settings") as mock_settings, \
         patch("app.services.kakao.httpx.AsyncClient") as mock_client_cls:
        mock_settings.kakao_rest_api_key = "test-key"
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with pytest.raises(Exception) as exc_info:
            await geocode("서울시 강남구")

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "geocoding_upstream_error"


@pytest.mark.asyncio
async def test_geocode_network_error():
    with patch("app.services.kakao.settings") as mock_settings, \
         patch("app.services.kakao.httpx.AsyncClient") as mock_client_cls:
        mock_settings.kakao_rest_api_key = "test-key"
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("연결 실패"))
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with pytest.raises(Exception) as exc_info:
            await geocode("서울시 강남구")

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "geocoding_upstream_error"


@pytest.mark.asyncio
async def test_geocode_not_configured():
    with patch("app.services.kakao.settings") as mock_settings:
        mock_settings.kakao_rest_api_key = ""

        with pytest.raises(Exception) as exc_info:
            await geocode("서울시 강남구")

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "geocoding_not_configured"
