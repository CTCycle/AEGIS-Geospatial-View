from __future__ import annotations

import asyncio
import math
from typing import Any
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from shapely.geometry import Point

from server.common.typing import is_json_array, is_json_object, json_object
from server.services.catalog.loader import find_macro_region_entry
from server.services.geospatial.land_mask import land_mask

from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderInvalidQueryError,
    ProviderMalformedPayloadError,
    ProviderRequest,
    ProviderResponse,
)
from server.services.geospatial.providers.http import (
    JsonFetcher,
    call_json_fetcher,
    fetch_json_url,
)
from server.services.geospatial.spatial_constraints import geodesic_distance_m

EARTHQUAKE_FDSN_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"
EARTHQUAKE_RANGE_LIMIT = 2000
EARTHQUAKE_RANGE_MAX_DAYS = 366
# Events within about 50 km of a macro region's member countries count as in it.
REGION_OFFSHORE_BUFFER_DEG = 0.5

###############################################################################
class USGSProvider(GeospatialProvider):
    provider_id = "usgs"
    # FDSN event-catalog identity; EMSC reuses the range path with its own.
    FDSN_URL = EARTHQUAKE_FDSN_URL
    FDSN_FORMAT = "geojson"
    CATALOG_NAME = "USGS earthquake catalog"
    ATTRIBUTION = "U.S. Geological Survey"
    COMPLETENESS_NOTE = (
        "Outside the US the catalog is generally complete only from about M4.5; "
        "smaller events are sparse and counts are lower bounds."
    )
    WATER_DATA_ITEMS_URL = (
        "https://api.waterdata.usgs.gov/ogcapi/v0/collections/latest-continuous/items"
    )

    # -------------------------------------------------------------------------
    def __init__(self, *, fetcher: JsonFetcher | None = None) -> None:
        self.fetcher = fetcher or fetch_json_url

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        if request.capability_id == "usgs_water_gauges":
            return await self._water_services(request)
        return await self._earthquakes(request)

    # -------------------------------------------------------------------------
    async def _earthquakes(self, request: ProviderRequest) -> ProviderResponse:
        if request.time is not None:
            return await self._earthquake_range(request)
        feed = str(request.params.get("feed") or "all_day").strip()
        features_url = (
            f"https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/{feed}.geojson"
        )
        if request.params.get("live"):
            payload = await call_json_fetcher(self.fetcher, features_url)
            features = _normalize_earthquake_features(payload)
            features = _filter_features_to_bbox(features, request.bbox)
            features = _filter_features_to_radius(features, request.params)
            minimum = _min_magnitude(request)
            if minimum is not None:
                features = [item for item in features if (magnitude := _float_or_none(item.get("magnitude"))) is not None and magnitude >= minimum]
            return ProviderResponse(
                capability_id=request.capability_id,
                provider_id=self.provider_id,
                payload={
                    "renderingMode": "clustered-points",
                    "features": features,
                    "totalResults": len(features),
                    "timeMode": "current",
                    "legend": {"type": "magnitude", "label": "Earthquake magnitude"},
                    "freshnessLabel": "USGS all-day earthquake feed",
                },
                attribution=["U.S. Geological Survey"],
                result_status="valid_empty" if not features else "ok",
                result_type="features",
                coverage=_earthquake_coverage(request, truncated=False, note=self.COMPLETENESS_NOTE),
            )
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "clustered-points",
                "featuresUrl": features_url,
                "timeMode": "current",
                "legend": {"type": "magnitude", "label": "Earthquake magnitude"},
                "freshnessLabel": "USGS all-day earthquake feed",
            },
            attribution=["U.S. Geological Survey"],
            result_type="metadata",
        )

    # -------------------------------------------------------------------------
    async def _earthquake_range(self, request: ProviderRequest) -> ProviderResponse:
        start, end = _resolve_time_range(request)
        features_url = _fdsn_event_url(
            start, end, request.bbox, _min_magnitude(request),
            base_url=self.FDSN_URL, response_format=self.FDSN_FORMAT,
        )
        label = f"{self.CATALOG_NAME} {start.date()} to {end.date()}"
        payload: dict[str, object] = {
            "renderingMode": "clustered-points",
            "timeMode": "historical",
            "legend": {"type": "magnitude", "label": "Earthquake magnitude"},
            "freshnessLabel": label,
        }
        if not request.params.get("live"):
            payload["featuresUrl"] = features_url
            return ProviderResponse(
                capability_id=request.capability_id,
                provider_id=self.provider_id,
                payload=payload,
                attribution=[self.ATTRIBUTION],
                result_type="metadata",
                source_url=features_url,
            )
        raw = await call_json_fetcher(self.fetcher, features_url)
        features = self._normalize_events(raw)
        truncated = len(features) >= EARTHQUAKE_RANGE_LIMIT
        features = _filter_features_to_bbox(features, request.bbox)
        features = _filter_features_to_radius(features, request.params)
        features, region_coverage = await _filter_features_to_region(features, request)
        times = [
            value
            for value in (feature.get("time") for feature in features)
            if isinstance(value, int | float)
        ]
        observation_time = (
            datetime.fromtimestamp(max(times) / 1000, UTC).isoformat()
            if times
            else None
        )
        payload.update({"features": features, "totalResults": len(features)})
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload=payload,
            attribution=[self.ATTRIBUTION],
            warnings=(
                [
                    f"Result capped at {EARTHQUAKE_RANGE_LIMIT} events (most recent "
                    "first); narrow the area or period for the full list."
                ]
                if truncated
                else []
            ),
            result_status="valid_empty" if not features else "ok",
            result_type="features",
            observation_time=observation_time,
            coverage={**_earthquake_coverage(request, truncated=truncated, note=self.COMPLETENESS_NOTE),
                      **region_coverage, "temporal_scope_satisfied": True},
            source_url=features_url,
        )

    # -------------------------------------------------------------------------
    def _normalize_events(self, payload: object) -> list[dict[str, object]]:
        return _normalize_earthquake_features(payload)

    # -------------------------------------------------------------------------
    async def _water_services(self, request: ProviderRequest) -> ProviderResponse:
        params: dict[str, str | int] = {
            "f": "json",
            "limit": max(1, min(int(request.params.get("limit") or 1000), 10000)),
            "parameter_code": str(request.params.get("parameterCd") or "00065"),
        }
        if request.bbox is not None:
            west, south, east, north = request.bbox
            params["bbox"] = f"{west},{south},{east},{north}"
        features_url = f"{self.WATER_DATA_ITEMS_URL}?{urlencode(params)}"
        if request.params.get("live"):
            payload = await call_json_fetcher(self.fetcher, features_url)
            features = _normalize_water_gauge_features(payload)
            features = _filter_features_to_bbox(features, request.bbox)
            features = _filter_features_to_radius(features, request.params)
            return ProviderResponse(
                capability_id=request.capability_id,
                provider_id=self.provider_id,
                payload={
                    "renderingMode": "clustered-points",
                    "features": features,
                    "totalResults": len(features),
                    "format": "geojson",
                    "legend": {
                        "type": "water-level",
                        "label": "Latest gauge observation",
                    },
                    "freshnessLabel": "USGS latest-continuous observations",
                },
                attribution=["U.S. Geological Survey"],
                result_status="valid_empty" if not features else "ok",
                result_type="features",
            )
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "clustered-points",
                "featuresUrl": features_url,
                "format": "geojson",
                "legend": {"type": "water-level", "label": "Latest gauge observation"},
                "freshnessLabel": "USGS latest-continuous observations",
            },
            attribution=["U.S. Geological Survey"],
            result_type="metadata",
        )

###############################################################################
def _resolve_time_range(request: ProviderRequest) -> tuple[datetime, datetime]:
    start = request.time
    if start is None:
        raise ProviderInvalidQueryError("A start time is required.")
    end_value = request.params.get("end_time_iso")
    try:
        end = (
            datetime.fromisoformat(str(end_value).replace("Z", "+00:00"))
            if end_value
            else datetime.now(UTC)
        )
    except ValueError as exc:
        raise ProviderInvalidQueryError("The end time must be ISO-8601.") from exc
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    if end <= start:
        raise ProviderInvalidQueryError("The end time must follow the start time.")
    if end - start > timedelta(days=EARTHQUAKE_RANGE_MAX_DAYS):
        raise ProviderInvalidQueryError(
            f"Earthquake ranges are limited to {EARTHQUAKE_RANGE_MAX_DAYS} days."
        )
    return start, end

###############################################################################
def _fdsn_event_url(
    start: datetime,
    end: datetime,
    bbox: tuple[float, float, float, float] | None,
    min_magnitude: float | None = None,
    *,
    base_url: str = EARTHQUAKE_FDSN_URL,
    response_format: str = "geojson",
) -> str:
    query: dict[str, str | int | float] = {
        "format": response_format,
        "starttime": start.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S"),
        "endtime": end.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S"),
        "orderby": "time",
        "limit": EARTHQUAKE_RANGE_LIMIT,
    }
    if min_magnitude is not None:
        query["minmagnitude"] = min_magnitude
    # FDSN cannot express antimeridian-crossing boxes; those are filtered locally.
    if bbox is not None and bbox[0] <= bbox[2]:
        query.update(
            minlongitude=bbox[0],
            minlatitude=bbox[1],
            maxlongitude=bbox[2],
            maxlatitude=bbox[3],
        )
    return f"{base_url}?{urlencode(query)}"

###############################################################################
def _normalize_earthquake_features(payload: object) -> list[dict[str, object]]:
    if not is_json_object(payload):
        raise ProviderMalformedPayloadError(
            "USGS earthquake payload must be a GeoJSON object."
        )
    raw_features = payload.get("features")
    if not is_json_array(raw_features):
        raise ProviderMalformedPayloadError(
            "USGS earthquake payload is missing features."
        )
    features: list[dict[str, object]] = []
    for item in raw_features:
        if not is_json_object(item):
            continue
        properties = json_object(item.get("properties"))
        geometry = json_object(item.get("geometry"))
        coordinates = geometry.get("coordinates")
        if not is_json_array(coordinates) or len(coordinates) < 2:
            continue
        longitude, latitude = coordinates[0], coordinates[1]
        if not _valid_coordinates(latitude, longitude):
            continue
        features.append(
            {
                "id": str(item.get("id") or properties.get("code") or ""),
                "name": properties.get("place"),
                "category": "earthquake",
                "latitude": float(latitude),
                "longitude": float(longitude),
                "magnitude": properties.get("mag"),
                "time": properties.get("time"),
                "url": properties.get("url"),
                "metadata": {
                    "status": properties.get("status"),
                    "type": properties.get("type"),
                    "tsunami": properties.get("tsunami"),
                },
            }
        )
    return features

###############################################################################
def _normalize_water_gauge_features(payload: object) -> list[dict[str, object]]:
    if not is_json_object(payload) or payload.get("type") != "FeatureCollection":
        raise ProviderMalformedPayloadError(
            "USGS latest-continuous payload must be a GeoJSON FeatureCollection."
        )
    raw_features = payload.get("features")
    if not is_json_array(raw_features):
        raise ProviderMalformedPayloadError(
            "USGS latest-continuous payload is missing features."
        )
    features: list[dict[str, object]] = []
    for raw_feature in raw_features:
        feature = json_object(raw_feature)
        geometry = json_object(feature.get("geometry"))
        properties = json_object(feature.get("properties"))
        coordinates = geometry.get("coordinates")
        if not is_json_array(coordinates) or len(coordinates) < 2:
            continue
        longitude, latitude = coordinates[0], coordinates[1]
        value = _float_or_none(properties.get("value"))
        if not _valid_coordinates(latitude, longitude) or value is None:
            continue
        station_id = (
            properties.get("monitoring_location_id")
            or properties.get("monitoringLocationId")
            or feature.get("id")
        )
        features.append(
            {
                "id": str(station_id or ""),
                "name": properties.get("monitoring_location_name")
                or properties.get("name")
                or station_id,
                "category": "water_gauge",
                "latitude": float(latitude),
                "longitude": float(longitude),
                "value": value,
                "timestamp": properties.get("time"),
                "metadata": {
                    "parameterCode": properties.get("parameter_code"),
                    "unit": properties.get("unit_of_measure"),
                    "observedProperty": properties.get("observed_property"),
                    "verticalDatum": properties.get("vertical_datum"),
                    "huc": properties.get("huc"),
                },
            }
        )
    return features

###############################################################################
def _float_or_none(value: object) -> float | None:
    if not isinstance(value, int | float | str):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None

###############################################################################
def _valid_coordinates(latitude: object, longitude: object) -> bool:
    return (
        isinstance(latitude, int | float)
        and not isinstance(latitude, bool)
        and isinstance(longitude, int | float)
        and not isinstance(longitude, bool)
        and math.isfinite(float(latitude))
        and math.isfinite(float(longitude))
        and -90.0 <= float(latitude) <= 90.0
        and -180.0 <= float(longitude) <= 180.0
    )

###############################################################################
def _filter_features_to_bbox(
    features: list[dict[str, object]],
    bbox: tuple[float, float, float, float] | None,
) -> list[dict[str, object]]:
    if bbox is None:
        return features
    west, south, east, north = bbox
    filtered: list[dict[str, object]] = []
    for feature in features:
        latitude = _float_or_none(feature.get("latitude"))
        longitude = _float_or_none(feature.get("longitude"))
        if (
            latitude is not None
            and longitude is not None
            and south <= latitude <= north
            and (
                west <= longitude <= east
                if west <= east
                else longitude >= west or longitude <= east
            )
        ):
            filtered.append(feature)
    return filtered

###############################################################################
def _filter_features_to_radius(
    features: list[dict[str, object]],
    params: dict[str, object],
) -> list[dict[str, object]]:
    """Apply the exact requested radius after the bbox prefilter."""

    latitude = _float_or_none(params.get("latitude"))
    longitude = _float_or_none(params.get("longitude"))
    radius_m = _float_or_none(params.get("radius_m"))
    if (
        latitude is None
        or longitude is None
        or radius_m is None
        or radius_m <= 0
        or not _valid_coordinates(latitude, longitude)
    ):
        return features
    return [
        feature
        for feature in features
        if (
            (feature_latitude := _float_or_none(feature.get("latitude"))) is not None
            and (feature_longitude := _float_or_none(feature.get("longitude"))) is not None
            and geodesic_distance_m(
                latitude,
                longitude,
                feature_latitude,
                feature_longitude,
            )
            <= radius_m
        )
    ]


###############################################################################
async def _filter_features_to_region(
    features: list[dict[str, object]], request: ProviderRequest
) -> tuple[list[dict[str, object]], dict[str, Any]]:
    """Keep events on or near a macro region's member countries.

    A bbox alone over-covers (Europe would include Anatolia); the offshore
    buffer keeps events just off member coasts.
    """

    region = find_macro_region_entry(str(request.params.get("macro_region") or ""))
    if region is None or not region.countries or request.bbox is None:
        return features, {}
    mask = await asyncio.to_thread(land_mask, request.bbox, region.countries, REGION_OFFSHORE_BUFFER_DEG)
    kept = [
        feature for feature in features
        if (latitude := _float_or_none(feature.get("latitude"))) is not None
        and (longitude := _float_or_none(feature.get("longitude"))) is not None
        and mask.contains(Point(longitude, latitude))
    ]
    return kept, {"region": region.name, "region_offshore_buffer_deg": REGION_OFFSHORE_BUFFER_DEG,
                  "excluded_outside_region_events": len(features) - len(kept)}


###############################################################################
def _min_magnitude(request: ProviderRequest) -> float | None:
    filters = request.params.get("filters")
    value = filters.get("min_magnitude") if is_json_object(filters) else None
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ProviderInvalidQueryError("min_magnitude must be numeric.") from exc
    if not math.isfinite(number):
        raise ProviderInvalidQueryError("min_magnitude must be finite.")
    return number


###############################################################################
def _earthquake_coverage(request: ProviderRequest, *, truncated: bool, note: str) -> dict[str, Any]:
    return {"bbox": list(request.bbox) if request.bbox else None,
            "min_magnitude": _min_magnitude(request), "truncated": truncated,
            "value_kind": "observation", "completeness_note": note}
