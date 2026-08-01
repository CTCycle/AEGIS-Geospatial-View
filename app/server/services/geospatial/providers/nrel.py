from __future__ import annotations

from server.common.typing import is_json_array, is_json_object

import os
import json
import csv
import io
from pathlib import Path
from urllib.parse import urlencode

from server.services.geospatial.cache import CacheLookupStatus, GeospatialCache
from server.services.geospatial.normalizers import normalize_poi_category
from server.services.geospatial.providers._request import (
    request_center,
    request_radius_m,
)
from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderAuthError,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
    ProviderUnavailableError,
)
from server.services.geospatial.providers.http import (
    JsonFetcher,
    call_json_fetcher,
    fetch_json_url,
)

###############################################################################
class NRELProvider(GeospatialProvider):
    provider_id = "nrel"

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        api_key: str | None = None,
        fetcher: JsonFetcher | None = None,
        cache: GeospatialCache | None = None,
        snapshot_path: str | Path | None = None,
    ) -> None:
        self.api_key = api_key
        self.fetcher = fetcher or fetch_json_url
        self.cache = cache or GeospatialCache()
        self.snapshot_path = Path(snapshot_path or os.getenv("AEGIS_AFDC_SNAPSHOT_PATH", "")).expanduser() if (snapshot_path or os.getenv("AEGIS_AFDC_SNAPSHOT_PATH", "").strip()) else None

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        api_key = (self.api_key or os.getenv("NREL_API_KEY") or "").strip()
        snapshot = request.params.get("snapshot_path") or self.snapshot_path
        if snapshot:
            snapshot_path = Path(str(snapshot)).expanduser()
            if not snapshot_path.is_file():
                raise ProviderUnavailableError("Configured AFDC snapshot does not exist.")
            try:
                raw = snapshot_path.read_text(encoding="utf-8-sig")
                payload = json.loads(raw) if snapshot_path.suffix.lower() == ".json" else {"fuel_stations": list(csv.DictReader(io.StringIO(raw)))}
            except (OSError, UnicodeError, json.JSONDecodeError, csv.Error) as exc:
                raise ProviderUnavailableError("AFDC snapshot is unavailable or malformed.") from exc
            latitude, longitude = request_center(request)
            radius_m = request_radius_m(request, 10000.0)
            features = _filter_features(self._features(payload), request, latitude, longitude, radius_m)
            return ProviderResponse(
                capability_id=request.capability_id,
                provider_id=self.provider_id,
                payload={
                    "renderingMode": "clustered-points",
                    "sourceMode": "local-snapshot",
                    "snapshotPath": str(snapshot_path),
                    "features": features,
                    "featureCount": len(features),
                    "center": {"latitude": latitude, "longitude": longitude},
                    "radiusM": radius_m,
                },
                attribution=["National Renewable Energy Laboratory"],
            )
        if not api_key:
            raise ProviderAuthError("NREL_API_KEY is required for AFDC alternative fuel station access.")
        latitude, longitude = request_center(request)
        radius_m = request_radius_m(request, 10000.0)
        params = {
            "api_key": api_key,
            "latitude": f"{latitude:.6f}",
            "longitude": f"{longitude:.6f}",
            "radius": f"{radius_m / 1609.344:.1f}",
            "format": "json",
        }
        url = f"https://developer.nrel.gov/api/alt-fuel-stations/v1/nearest.json?{urlencode(params)}"
        if not bool(request.params.get("live")):
            return ProviderResponse(
                capability_id=request.capability_id,
                provider_id=self.provider_id,
                payload={
                    "renderingMode": "clustered-points",
                    "featuresUrl": url,
                },
                attribution=["National Renewable Energy Laboratory"],
            )
        cache_key = f"{self.provider_id}:{url}"
        try:
            payload = await call_json_fetcher(self.fetcher, url, None)
            features = self._features(payload)
            normalized = {
                "renderingMode": "clustered-points",
                "features": features,
                "featureCount": len(features),
                "center": {"latitude": latitude, "longitude": longitude},
                "radiusM": radius_m,
            }
            self.cache.set(cache_key, normalized, ttl_seconds=3600, stale_while_revalidate_seconds=86400)
            return ProviderResponse(
                capability_id=request.capability_id,
                provider_id=self.provider_id,
                payload=normalized,
                attribution=["National Renewable Energy Laboratory"],
            )
        except (ProviderError, ValueError) as exc:
            cached = self.cache.get(cache_key)
            if cached.status == CacheLookupStatus.STALE and is_json_object(cached.value):
                return ProviderResponse(
                    capability_id=request.capability_id,
                    provider_id=self.provider_id,
                    payload=cached.value,
                    attribution=["National Renewable Energy Laboratory"],
                    warnings=["NREL AFDC request failed; serving stale cached stations."],
                    stale=True,
                )
            if isinstance(exc, ProviderError):
                raise
            raise ProviderUnavailableError(str(exc)) from exc

    # -------------------------------------------------------------------------
    def _features(self, payload: object) -> list[dict[str, object]]:
        if not is_json_object(payload):
            raise ValueError("NREL AFDC payload must be an object.")
        stations = payload.get("fuel_stations")
        if not is_json_array(stations):
            return []
        features: list[dict[str, object]] = []
        for station in stations:
            if not is_json_object(station):
                continue
            latitude = station.get("latitude")
            longitude = station.get("longitude")
            try:
                latitude_value = float(str(latitude))
                longitude_value = float(str(longitude))
            except (TypeError, ValueError):
                continue
            fuel_type = str(station.get("fuel_type_code") or "fuel")
            features.append(
                {
                    "id": str(station.get("id") or ""),
                    "name": station.get("station_name"),
                    "category": normalize_poi_category("ev_charging" if fuel_type == "ELEC" else "fuel"),
                    "source": self.provider_id,
                    "latitude": latitude_value,
                    "longitude": longitude_value,
                    "address": station.get("street_address"),
                    "phone": station.get("station_phone"),
                    "metadata": {
                        "fuelType": fuel_type,
                        "access": station.get("access_code"),
                        "status": station.get("status_code"),
                    },
                }
            )
        return features

###############################################################################
def _filter_features(
    features: list[dict[str, object]],
    request: ProviderRequest,
    latitude: float,
    longitude: float,
    radius_m: float,
) -> list[dict[str, object]]:
    del latitude, longitude, radius_m
    if request.bbox is None:
        return features[: int(request.params.get("limit") or 100)]
    west, south, east, north = request.bbox
    return [
        item
        for item in features
        if west <= float(str(item["longitude"])) <= east and south <= float(str(item["latitude"])) <= north
    ][: int(request.params.get("limit") or 100)]
