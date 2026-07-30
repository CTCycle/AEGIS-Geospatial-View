from __future__ import annotations

import os
from urllib.parse import urlencode

from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderAuthError,
    ProviderRequest,
    ProviderResponse,
)
from server.services.geospatial.providers.http import (
    JsonFetcher,
    call_json_fetcher,
    fetch_json_url,
)

FRED_SERIES_SEARCH_ENDPOINT = "https://api.stlouisfed.org/fred/series/search"
DEFAULT_SEARCH_TEXT = "housing price rent income"

###############################################################################
class FREDProvider(GeospatialProvider):
    """Credentialed FRED series discovery for dynamic market searches."""

    provider_id = "fred"

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        api_key: str | None = None,
        fetcher: JsonFetcher | None = None,
    ) -> None:
        self.api_key = (api_key or os.getenv("FRED_API_KEY") or "").strip()
        self.fetcher = fetcher or fetch_json_url

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        if not self.api_key:
            raise ProviderAuthError("FRED API key is required.")
        search_text = str(
            request.params.get("search_text")
            or request.params.get("query")
            or DEFAULT_SEARCH_TEXT
        ).strip()
        limit = max(1, min(int(request.params.get("limit") or 25), 1000))
        if not request.params.get("live"):
            return ProviderResponse(
                capability_id=request.capability_id,
                provider_id=self.provider_id,
                payload={
                    "renderingMode": "metadata-only",
                    "source": "Federal Reserve Bank of St. Louis FRED",
                    "searchEndpoint": "/api/geospatial/providers/fred/search",
                    "credentialPolicy": "server-side-only",
                },
                attribution=["Federal Reserve Bank of St. Louis FRED"],
            )
        params = urlencode(
            {
                "search_text": search_text,
                "api_key": self.api_key,
                "file_type": "json",
                "limit": str(limit),
            }
        )
        payload = await call_json_fetcher(
            self.fetcher,
            f"{FRED_SERIES_SEARCH_ENDPOINT}?{params}",
        )
        series = _normalize_series(payload)
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "metadata-only",
                "source": "Federal Reserve Bank of St. Louis FRED",
                "query": search_text,
                "series": series,
                "totalResults": len(series),
                "credentialPolicy": "server-side-only",
            },
            attribution=["Federal Reserve Bank of St. Louis FRED"],
        )

###############################################################################
def _normalize_series(payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, dict):
        return []
    raw_series = payload.get("seriess")
    if not isinstance(raw_series, list):
        return []
    normalized: list[dict[str, object]] = []
    for item in raw_series:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        normalized.append(
            {
                "id": str(item["id"]),
                "title": item.get("title"),
                "frequency": item.get("frequency_short") or item.get("frequency"),
                "units": item.get("units_short") or item.get("units"),
                "seasonalAdjustment": item.get("seasonal_adjustment_short")
                or item.get("seasonal_adjustment"),
                "observationStart": item.get("observation_start"),
                "observationEnd": item.get("observation_end"),
                "lastUpdated": item.get("last_updated"),
                "popularity": item.get("popularity"),
            }
        )
    return normalized
