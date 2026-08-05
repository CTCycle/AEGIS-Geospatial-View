from __future__ import annotations

import asyncio

import pytest

from server.services.geospatial.providers.base import ProviderAuthError, ProviderRequest
from server.services.geospatial.providers.fred import FREDProvider

###############################################################################
def test_fred_requires_key_for_live_search() -> None:
    with pytest.raises(ProviderAuthError, match="FRED_API_KEY|FRED API key"):
        asyncio.run(
            FREDProvider().fetch(
                ProviderRequest(
                    capability_id="fred_regional_market_indicators",
                    params={"live": True, "search_text": "housing"},
                )
            )
        )

###############################################################################
def test_fred_normalizes_series_search_payload() -> None:
    seen: dict[str, object] = {}

    async def fetcher(url: str, headers: dict[str, str] | None = None) -> object:
        seen["url"] = url
        seen["headers"] = headers
        return {
            "seriess": [
                {
                    "id": "HOUST",
                    "title": "Housing Starts",
                    "frequency_short": "M",
                    "units_short": "Thousands of Units",
                    "observation_start": "1959-01-01",
                    "observation_end": "2026-01-01",
                    "last_updated": "2026-02-01 08:00:00-05:00",
                }
            ]
        }

    response = asyncio.run(
        FREDProvider(api_key="fred-test", fetcher=fetcher).fetch(
            ProviderRequest(
                capability_id="fred_regional_market_indicators",
                params={"live": True, "search_text": "housing", "limit": 10},
            )
        )
    )

    assert response.payload["totalResults"] == 1
    assert response.payload["series"] == [
        {
            "id": "HOUST",
            "title": "Housing Starts",
            "frequency": "M",
            "units": "Thousands of Units",
            "seasonalAdjustment": None,
            "observationStart": "1959-01-01",
            "observationEnd": "2026-01-01",
            "lastUpdated": "2026-02-01 08:00:00-05:00",
            "popularity": None,
        }
    ]
    assert "api_key=fred-test" in str(seen["url"])
