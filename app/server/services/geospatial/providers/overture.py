from __future__ import annotations

from server.common.typing import is_json_array, is_json_object, json_array, json_object

import json
import os
from pathlib import Path
from typing import Any

from server.common.paths import resolve_runtime_data_root
from server.services.geospatial.normalizers import (
    NormalizationError,
    deduplicate_poi_features,
    normalize_poi_category,
    normalize_poi_feature,
)
from server.services.geospatial.overpass import (
    OverpassRateLimitError,
    OverpassService,
    OverpassServiceError,
)
from server.services.geospatial.providers._request import (
    request_center,
    request_radius_m,
)
from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderRateLimitError,
    ProviderRequest,
    ProviderResponse,
    ProviderUnavailableError,
)


###############################################################################
class OvertureProvider(GeospatialProvider):
    """Query an ingested Overture Places GeoJSON index and optionally augment it with Overpass."""

    provider_id = "overture"

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        places_path: str | Path | None = None,
        overpass_service: OverpassService | None = None,
    ) -> None:
        self.places_path = Path(
            places_path
            or os.getenv(
                "AEGIS_OVERTURE_PLACES_INDEX",
                str(
                    resolve_runtime_data_root()
                    / "geospatial"
                    / "overture"
                    / "places.geojson"
                ),
            )
        ).expanduser()
        self.overpass_service = overpass_service or OverpassService()

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        source = Path(
            str(request.params.get("index_path") or self.places_path)
        ).expanduser()
        if not source.is_file():
            return ProviderResponse(
                capability_id=request.capability_id,
                provider_id=self.provider_id,
                payload={
                    "renderingMode": "clustered-points",
                    "status": "configuration-needed",
                    "source": "Overture Maps Places",
                    "message": (
                        "Ingest an Overture Places GeoJSON index and configure "
                        "AEGIS_OVERTURE_PLACES_INDEX before interactive POI queries."
                    ),
                    "features": [],
                    "totalResults": 0,
                },
                attribution=["Overture Maps Foundation"],
            )
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ProviderUnavailableError(
                "Overture Places index is unavailable or malformed."
            ) from exc
        if not is_json_object(payload) or not is_json_array(payload.get("features")):
            raise ProviderUnavailableError(
                "Overture Places index must be a GeoJSON FeatureCollection."
            )

        features = self._features(payload["features"], request)
        warnings: list[str] = []
        if _is_true(request.params.get("augment_overpass")):
            try:
                features.extend(await self._overpass_features(request))
            except OverpassRateLimitError as exc:
                raise ProviderRateLimitError(str(exc)) from exc
            except (OverpassServiceError, ValueError) as exc:
                warnings.append(f"Overpass augmentation unavailable: {exc}")
        deduplicated = deduplicate_poi_features(features)
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "clustered-points",
                "source": "Overture Maps Places",
                "indexPath": str(source),
                "features": [item.model_dump(mode="json") for item in deduplicated],
                "totalResults": len(deduplicated),
                "augmentation": "overpass"
                if _is_true(request.params.get("augment_overpass"))
                else "none",
            },
            attribution=[
                "Overture Maps Foundation",
                "© OpenStreetMap contributors (ODbL)"
                if _is_true(request.params.get("augment_overpass"))
                else "",
            ],
            warnings=[item for item in warnings if item],
        )

    # -------------------------------------------------------------------------
    async def _overpass_features(self, request: ProviderRequest) -> list[Any]:
        latitude, longitude = request_center(request)
        payload = await self.overpass_service.get_nearby_poi(
            latitude=latitude,
            longitude=longitude,
            radius_m=request_radius_m(request, self.overpass_service.default_radius_m),
            amenity_tags=_amenity_tags(request),
            limit=_optional_int(request.params.get("limit")),
        )
        features: list[Any] = []
        for item in json_array(payload.get("items")):
            item = json_object(item)
            if not item:
                continue
            try:
                features.append(
                    normalize_poi_feature(
                        {**item, "category": item.get("amenity")},
                        source="overpass",
                        category=normalize_poi_category(
                            str(item.get("amenity") or "amenity")
                        ),
                    )
                )
            except NormalizationError:
                continue
        return features

    # -------------------------------------------------------------------------
    def _features(
        self, raw_features: list[object], request: ProviderRequest
    ) -> list[Any]:
        query = str(request.params.get("query") or "").strip().casefold()
        category = str(request.params.get("category") or "").strip().casefold()
        limit = max(1, min(500, _optional_int(request.params.get("limit")) or 100))
        features: list[Any] = []
        for raw in raw_features:
            raw = json_object(raw)
            if not raw:
                continue
            properties = json_object(raw.get("properties"))
            geometry = json_object(raw.get("geometry"))
            coordinates = geometry.get("coordinates")
            if not is_json_array(coordinates) or len(coordinates) < 2:
                continue
            try:
                longitude, latitude = (
                    float(str(coordinates[0])),
                    float(str(coordinates[1])),
                )
            except TypeError, ValueError:
                continue
            if request.bbox and not _in_bbox(longitude, latitude, request.bbox):
                continue
            name = str(
                properties.get("name") or properties.get("names.primary") or ""
            ).strip()
            raw_category = str(
                properties.get("category")
                or properties.get("categories.primary")
                or "amenity"
            )
            normalized_category = normalize_poi_category(raw_category)
            if query and query not in f"{name} {raw_category}".casefold():
                continue
            if category and category not in {
                raw_category.casefold(),
                normalized_category.casefold(),
            }:
                continue
            candidate = {
                "id": raw.get("id") or properties.get("id"),
                "name": name or None,
                "latitude": latitude,
                "longitude": longitude,
                "category": normalized_category,
                "address": properties.get("address")
                or properties.get("addresses.primary"),
                "website": properties.get("website")
                or properties.get("websites.primary"),
                "phone": properties.get("phone"),
                "metadata": {
                    "confidence": properties.get("confidence"),
                    "sources": properties.get("sources"),
                    "overtureCategory": raw_category,
                },
            }
            try:
                features.append(
                    normalize_poi_feature(
                        candidate, source=self.provider_id, category=normalized_category
                    )
                )
            except NormalizationError:
                continue
            if len(features) >= limit:
                break
        return features


###############################################################################
def _in_bbox(
    longitude: float, latitude: float, bbox: tuple[float, float, float, float]
) -> bool:
    west, south, east, north = bbox
    return west <= longitude <= east and south <= latitude <= north


###############################################################################
def _amenity_tags(request: ProviderRequest) -> list[str] | None:
    value = request.params.get("amenity_tags")
    return [str(item) for item in value] if is_json_array(value) else None


###############################################################################
def _optional_int(value: object) -> int | None:
    try:
        return int(str(value)) if value is not None else None
    except TypeError, ValueError:
        return None


###############################################################################
def _is_true(value: object) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes"}
