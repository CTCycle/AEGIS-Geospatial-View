"""geoBoundaries open administrative boundaries (gbOpen), simplified geometry.

The API returns per-country metadata whose geometry link is a GitHub ``raw``
URL that redirects to Git LFS media. The shared HTTP client never follows
redirects, so the adapter rewrites only that exact repository prefix to its
media host and refuses any other geometry location.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from shapely.geometry import box

from server.common.typing import is_json_array, is_json_object, json_object
from server.services.catalog.loader import country_iso3
from server.services.geospatial.geometry_ops import record_geometry
from server.services.geospatial.land_mask import country_at
from server.services.geospatial.providers.base import (
    ProviderInvalidQueryError,
    ProviderMalformedPayloadError,
    ProviderRequest,
    ProviderResponse,
)
from server.services.geospatial.providers.http import fetch_bytes_url

GEOBOUNDARIES_API_URL = "https://www.geoboundaries.org/api/current/gbOpen"
GITHUB_RAW_PREFIX = "https://github.com/wmgeolab/geoBoundaries/raw/"
GITHUB_MEDIA_PREFIX = "https://media.githubusercontent.com/media/wmgeolab/geoBoundaries/"
GEOBOUNDARIES_ATTRIBUTION = "geoBoundaries (Runfola et al., CC BY 4.0)"
MAX_ADMIN_LEVEL = 5
MAX_ADMIN_UNITS = 1_000
MAX_GEOMETRY_BYTES = 12 * 1024 * 1024

BytesFetcher = Callable[[str, dict[str, str] | None], Awaitable[bytes]]


###############################################################################
class GeoBoundariesProvider:
    provider_id = "geoboundaries"

    # -------------------------------------------------------------------------
    def __init__(self, *, fetcher: BytesFetcher | None = None) -> None:
        self.fetcher: BytesFetcher = fetcher or _bounded_fetch

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        iso3 = _country(request)
        level = _admin_level(request.params.get("admin_level"))
        metadata_url = f"{GEOBOUNDARIES_API_URL}/{iso3}/ADM{level}/"
        metadata = _json(await self.fetcher(metadata_url, None))
        if not is_json_object(metadata):
            raise ProviderMalformedPayloadError("geoBoundaries metadata must be an object.")
        units = _int(metadata.get("admUnitCount"))
        if units is not None and units > MAX_ADMIN_UNITS:
            raise ProviderInvalidQueryError(
                f"{iso3} ADM{level} has {units} units (limit {MAX_ADMIN_UNITS}); use a lower admin_level."
            )
        geometry_url = media_url(str(metadata.get("simplifiedGeometryGeoJSON") or ""))
        collection = _json(await self.fetcher(geometry_url, None))
        features = _within_bbox(normalize_boundaries(collection, iso3=iso3, level=level), request.bbox)
        source = str(metadata.get("boundarySource") or "").strip()
        licence = str(metadata.get("boundaryLicense") or "").strip()
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "geojson",
                "type": "FeatureCollection",
                "features": features,
                "totalResults": len(features),
                "boundary": {"iso3": iso3, "admin_level": level,
                             "year": metadata.get("boundaryYearRepresented"),
                             "source": source or None, "licence": licence or None},
            },
            attribution=[GEOBOUNDARIES_ATTRIBUTION, *([f"Source: {source} ({licence})"] if source else [])],
            result_status="ok" if features else "valid_empty",
            result_type="features",
            coverage={"type": "country", "country_iso3": iso3, "admin_level": level,
                      "geometry": "simplified", "spatial_scope_satisfied": True},
            source_url=metadata_url,
        )


###############################################################################
def media_url(url: str) -> str:
    """Map the geoBoundaries GitHub raw link to its LFS media host, nothing else."""

    if not url.startswith(GITHUB_RAW_PREFIX) or ".." in url or "?" in url:
        raise ProviderMalformedPayloadError("geoBoundaries geometry link is not on the expected repository.")
    return GITHUB_MEDIA_PREFIX + url.removeprefix(GITHUB_RAW_PREFIX)


###############################################################################
def normalize_boundaries(payload: object, *, iso3: str, level: int) -> list[dict[str, object]]:
    if not is_json_object(payload) or not is_json_array(payload.get("features")):
        raise ProviderMalformedPayloadError("geoBoundaries geometry must be a GeoJSON FeatureCollection.")
    features: list[dict[str, object]] = []
    for item in json_object(payload).get("features", []):
        feature = json_object(item)
        geometry = feature.get("geometry")
        if not is_json_object(geometry) or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
            continue
        properties = json_object(feature.get("properties"))
        features.append({
            "type": "Feature",
            "id": properties.get("shapeID"),
            "geometry": geometry,
            "properties": {
                "name": properties.get("shapeName"),
                "shape_iso": properties.get("shapeISO") or None,
                "shape_id": properties.get("shapeID"),
                "admin_level": level,
                "country_iso3": iso3,
            },
        })
    return features


###############################################################################
def _country(request: ProviderRequest) -> str:
    named = request.params.get("country")
    if isinstance(named, str) and named.strip():
        code = country_iso3(named)
        if code is None:
            raise ProviderInvalidQueryError(f"Unknown country '{named}'.")
        return code
    masked = request.params.get("mask_countries")
    if is_json_array(masked) and len(masked) == 1 and (code := country_iso3(str(masked[0]))):
        return code
    point = _point(request)
    iso2 = country_at(*point) if point is not None else None
    code = country_iso3(iso2) if iso2 else None
    if code is None:
        raise ProviderInvalidQueryError("Administrative boundaries need a country or a location inside one.")
    return code


###############################################################################
def _point(request: ProviderRequest) -> tuple[float, float] | None:
    latitude, longitude = request.params.get("latitude"), request.params.get("longitude")
    if isinstance(latitude, int | float) and isinstance(longitude, int | float):
        return float(longitude), float(latitude)
    if request.bbox is not None:
        west, south, east, north = request.bbox
        return (west + east) / 2, (south + north) / 2
    return None


###############################################################################
def _admin_level(value: object) -> int:
    if value is None:
        return 1
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_ADMIN_LEVEL:
        raise ProviderInvalidQueryError(f"admin_level must be an integer from 0 to {MAX_ADMIN_LEVEL}.")
    return value


###############################################################################
def _within_bbox(
    features: list[dict[str, object]], bbox: tuple[float, float, float, float] | None
) -> list[dict[str, object]]:
    if bbox is None:
        return features
    area = box(*bbox)
    return [item for item in features if (geometry := record_geometry(item)) is not None and geometry.intersects(area)]


###############################################################################
async def _bounded_fetch(url: str, headers: dict[str, str] | None = None) -> bytes:
    return await fetch_bytes_url(url, headers, max_bytes=MAX_GEOMETRY_BYTES)


###############################################################################
def _json(body: bytes) -> object:
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderMalformedPayloadError("geoBoundaries returned malformed JSON.") from exc


###############################################################################
def _int(value: object) -> int | None:
    try:
        return int(str(value))
    except ValueError:
        return None
