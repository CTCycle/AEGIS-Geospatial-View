from __future__ import annotations

import asyncio
import csv
import io
import os
import urllib.request
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlencode

from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderAuthError,
    ProviderRequest,
    ProviderResponse,
    ProviderUnavailableError,
)

TextFetcher = Callable[[str], Awaitable[str] | str]


class NASAFIRMSProvider(GeospatialProvider):
    provider_id = "nasa_firms"

    def __init__(
        self, *, api_key: str | None = None, fetcher: TextFetcher | None = None
    ) -> None:
        self.api_key = api_key
        self.fetcher = fetcher or _fetch_text_url

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        api_key = (self.api_key or os.getenv("NASA_API_KEY") or "").strip()
        if not api_key:
            raise ProviderAuthError("NASA_API_KEY is required for NASA FIRMS active fire access.")
        west, south, east, north = request.bbox or (-180.0, -90.0, 180.0, 90.0)
        params = urlencode({"bbox": f"{west},{south},{east},{north}", "key": api_key})
        features_url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{api_key}/VIIRS_SNPP_NRT/{west},{south},{east},{north}/1"
        if request.params.get("live"):
            csv_text = await _call_text_fetcher(self.fetcher, features_url)
            features = _normalize_firms_csv(csv_text)
            return ProviderResponse(
                capability_id=request.capability_id,
                provider_id=self.provider_id,
                payload={
                    "renderingMode": "clustered-points",
                    "features": features,
                    "totalResults": len(features),
                    "query": params,
                },
                attribution=["NASA FIRMS"],
            )
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "clustered-points",
                "featuresUrl": features_url,
                "query": params,
            },
            attribution=["NASA FIRMS"],
        )


async def _call_text_fetcher(fetcher: TextFetcher, url: str) -> str:
    value = fetcher(url)
    if hasattr(value, "__await__"):
        return await value
    return value


async def _fetch_text_url(url: str) -> str:
    return await asyncio.to_thread(_fetch_text_url_sync, url)


def _fetch_text_url_sync(url: str) -> str:
    with urllib.request.urlopen(url, timeout=20) as response:
        return response.read().decode("utf-8")


def _normalize_firms_csv(csv_text: str) -> list[dict[str, Any]]:
    try:
        rows = list(csv.DictReader(io.StringIO(csv_text)))
    except csv.Error as exc:
        raise ProviderUnavailableError("NASA FIRMS returned malformed CSV.") from exc
    features: list[dict[str, Any]] = []
    for row in rows:
        latitude = _float_or_none(row.get("latitude"))
        longitude = _float_or_none(row.get("longitude"))
        if latitude is None or longitude is None:
            continue
        features.append(
            {
                "id": row.get("fire_id")
                or f"firms:{latitude:.5f}:{longitude:.5f}:{row.get('acq_date', '')}:{row.get('acq_time', '')}",
                "name": "Active fire detection",
                "category": "active_fire",
                "latitude": latitude,
                "longitude": longitude,
                "brightness": _float_or_none(row.get("bright_ti4") or row.get("brightness")),
                "confidence": row.get("confidence"),
                "timestamp": _firms_timestamp(row),
                "metadata": {
                    "satellite": row.get("satellite"),
                    "instrument": row.get("instrument"),
                    "frp": _float_or_none(row.get("frp")),
                    "daynight": row.get("daynight"),
                },
            }
        )
    return features


def _firms_timestamp(row: dict[str, str]) -> str | None:
    date = (row.get("acq_date") or "").strip()
    time = (row.get("acq_time") or "").strip().zfill(4)
    if not date:
        return None
    if len(time) != 4:
        return date
    return f"{date}T{time[:2]}:{time[2:]}:00Z"


def _float_or_none(value: str | None) -> float | None:
    if value is None or not str(value).strip():
        return None
    try:
        return float(value)
    except ValueError:
        return None
