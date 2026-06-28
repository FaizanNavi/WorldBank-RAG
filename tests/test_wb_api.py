import pytest
import asyncio
import json
from unittest.mock import AsyncMock, patch, MagicMock
from app.tools.wb_api import WorldBankAPI
@pytest.fixture
def wb():
    return WorldBankAPI()
@pytest.mark.asyncio
async def test_fetch_indicator_success(wb):
    mock_response_data = [
        {"page": 1, "pages": 1, "total": 2},
        [
            {
                "indicator": {"id": "NY.GDP.PCAP.CD", "value": "GDP per capita"},
                "country": {"id": "IN", "value": "India"},
                "date": "2023",
                "value": 2500.5
            },
            {
                "indicator": {"id": "NY.GDP.PCAP.CD", "value": "GDP per capita"},
                "country": {"id": "IN", "value": "India"},
                "date": "2022",
                "value": 2400.3
            }
        ]
    ]
    with patch("aiohttp.ClientSession") as mock_session:
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=mock_response_data)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_session_instance = AsyncMock()
        mock_session_instance.get = MagicMock(return_value=mock_resp)
        mock_session_instance.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session_instance.__aexit__ = AsyncMock(return_value=False)
        mock_session.return_value = mock_session_instance
        result = await wb.fetch_indicator("IN", "NY.GDP.PCAP.CD")
    assert result["country"] == "IN"
    assert result["country_name"] == "India"
    assert len(result["data"]) == 2
    assert result["data"][0]["year"] == "2023"
    assert result["data"][0]["value"] == 2500.5
@pytest.mark.asyncio
async def test_fetch_indicator_empty_response(wb):
    mock_response_data = [{"page": 1}, None]
    with patch("aiohttp.ClientSession") as mock_session:
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=mock_response_data)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_session_instance = AsyncMock()
        mock_session_instance.get = MagicMock(return_value=mock_resp)
        mock_session_instance.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session_instance.__aexit__ = AsyncMock(return_value=False)
        mock_session.return_value = mock_session_instance
        result = await wb.fetch_indicator("XX", "INVALID")
    assert "error" in result
@pytest.mark.asyncio
async def test_compare_countries_parallel(wb):
    async def mock_fetch(country, indicator, start=2010, end=2024):
        return {
            "country": country,
            "country_name": country,
            "indicator": indicator,
            "data": [{"year": "2023", "value": 100}],
            "latency_ms": 100
        }
    wb.fetch_indicator = mock_fetch
    result = await wb.compare_countries(["IN", "CN", "US"], "NY.GDP.PCAP.CD")
    assert len(result["comparison"]) == 3
    assert result["countries_compared"] == ["IN", "CN", "US"]
    assert "parallel_latency_ms" in result
    assert "speedup_percent" in result
def test_cache_stats(wb):
    stats = wb.cache.get_stats()
    assert "hits" in stats
    assert "misses" in stats
    assert "hit_rate_percent" in stats
def test_metrics(wb):
    metrics = wb.get_metrics()
    assert "cache" in metrics
    assert "latency" in metrics
    assert "p50_ms" in metrics["latency"]
    assert "p95_ms" in metrics["latency"]
