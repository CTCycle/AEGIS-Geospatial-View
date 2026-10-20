from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from server.common.typing import is_json_array, is_json_object, json_object
from server.services.geospatial.providers.base import (
    ProviderMalformedPayloadError,
    ProviderRequest,
    ProviderResponse,
)
from server.services.geospatial.providers.http import JsonFetcher, fetch_bytes_url
from server.services.geospatial.providers.usgs import USGSProvider

EMSC_FDSN_URL = "https://www.seismicportal.eu/fdsnws/event/1/query"
EMSC_EVENT_URL = "https://www.seismicportal.eu/eventdetails.html?unid="

###############################################################################
async def fetch_emsc_json(url: str, headers: dict[str, str] | None = None) -> object:
    # The FDSN service answers an empty selection with HTTP 204 and no body.
    body = await fetch_bytes_url(url, headers)
    if not body.strip():
        return {"type": "FeatureCollection", "features": []}
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderMalformedPayloadError("Provider returned malformed JSON.") from exc

###############################################################################
class EMSCProvider(USGSProvider):
    """EMSC SeismicPortal FDSN events: denser Euro-Mediterranean coverage."""

    provider_id = "emsc"
    FDSN_URL = EMSC_FDSN_URL
    FDSN_FORMAT = "json"
    CATALOG_NAME = "EMSC earthquake catalog"
    ATTRIBUTION = "EMSC-CSEM SeismicPortal"
    COMPLETENESS_NOTE = (
        "Dense Euro-Mediterranean network: typically complete from about M2.5-3 "
        "in Europe and the Mediterranean, about M4.5 elsewhere; counts are lower bounds."
    )

    # -------------------------------------------------------------------------
    def __init__(self, *, fetcher: JsonFetcher | None = None) -> None:
        super().__init__(fetcher=fetcher or fetch_emsc_json)

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        # EMSC has no summary feeds: "current" is the last 24 hours of the catalog.
        if request.time is None:
            request = replace(request, time=datetime.now(UTC) - timedelta(days=1))
        return await self._earthquake_range(request)

    # -------------------------------------------------------------------------
    def _normalize_events(self, payload: object) -> list[dict[str, object]]:
        if not is_json_object(payload) or not is_json_array(payload.get("features")):
            raise ProviderMalformedPayloadError("EMSC payload must be a GeoJSON FeatureCollection.")
        features: list[dict[str, object]] = []
        for item in json_object(payload).get("features", []):
            properties = json_object(json_object(item).get("properties"))
            latitude, longitude = properties.get("lat"), properties.get("lon")
            if not (
                isinstance(latitude, int | float) and isinstance(longitude, int | float)
                and -90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0
            ):
                continue
            unid = str(properties.get("unid") or json_object(item).get("id") or "")
            event_time = properties.get("time")
            try:
                epoch_ms = int(datetime.fromisoformat(str(event_time).replace("Z", "+00:00")).timestamp() * 1000)
            except ValueError:
                continue
            region = str(properties.get("flynn_region") or "").title() or None
            features.append({
                "id": unid,
                "name": region,
                "category": "earthquake",
                "latitude": float(latitude),
                "longitude": float(longitude),
                "magnitude": properties.get("mag"),
                "time": epoch_ms,
                "url": f"{EMSC_EVENT_URL}{unid}" if unid else None,
                "metadata": {
                    "magnitude_type": properties.get("magtype"),
                    "depth_km": properties.get("depth"),
                    "authority": properties.get("auth"),
                    "type": properties.get("evtype"),
                },
            })
        return features
