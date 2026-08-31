from __future__ import annotations

from server.common.typing import is_json_array, json_array, json_object

from typing import Any

from server.services.geospatial.normalizers import (
    NormalizationError,
    normalize_poi_feature,
)
from server.services.geospatial.overpass import (
    OverpassRateLimitError,
    OverpassRequestError,
    OverpassService,
    OverpassServiceError,
)
from server.services.geospatial.providers._request import (
    request_center,
    request_radius_m,
)
from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderInvalidQueryError,
    ProviderRequest,
    ProviderRateLimitError,
    ProviderResponse,
    ProviderUnavailableError,
)

AMENITY_GROUPS = {
    "food": ["cafe", "restaurant", "bar", "fast_food"],
    "healthcare": ["hospital", "clinic", "pharmacy", "doctors"],
    "transit": ["bus_station", "train_station", "taxi", "ferry_terminal"],
    "education": ["school", "college", "university", "library"],
    "emergency": ["hospital", "fire_station", "police", "shelter"],
    "fuel": ["fuel", "charging_station"],
}


###############################################################################
class OverpassProvider(GeospatialProvider):
    provider_id = "overpass"

    # -------------------------------------------------------------------------
    def __init__(self, *, service: OverpassService | None = None) -> None:
        self.service = service or OverpassService()

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        latitude, longitude = request_center(request)
        radius_m = request_radius_m(request, self.service.default_radius_m)
        if request.capability_id == "overpass_residential_buildings":
            try:
                payload = await self.service.get_residential_buildings(
                    latitude=latitude,
                    longitude=longitude,
                    radius_m=radius_m,
                    limit=_optional_int(request.params.get("limit")),
                )
            except OverpassRateLimitError as exc:
                raise ProviderRateLimitError(str(exc)) from exc
            except OverpassRequestError as exc:
                raise ProviderInvalidQueryError(str(exc)) from exc
            except (OverpassServiceError, ValueError) as exc:
                raise ProviderUnavailableError(str(exc)) from exc
            return ProviderResponse(
                capability_id=request.capability_id,
                provider_id=self.provider_id,
                payload=payload,
                attribution=["© OpenStreetMap contributors (ODbL)"],
                coverage={
                    "type": "circle",
                    "center": {"latitude": latitude, "longitude": longitude},
                    "radius_m": radius_m,
                },
                spatial_resolution="building footprints",
                source_url=getattr(self.service, "base_url", None),
                result_type="features",
                result_status=(
                    "valid_empty"
                    if not json_array(payload.get("features"))
                    else "ok"
                ),
            )
        tags = request.params.get("amenity_tags")
        amenity_tags = [str(tag) for tag in tags] if is_json_array(tags) else None
        categories_value = request.params.get("poi_categories")
        categories = (
            [str(item) for item in categories_value]
            if is_json_array(categories_value)
            else None
        )
        if amenity_tags is None:
            category = str(request.params.get("category") or "").strip().lower()
            amenity_tags = AMENITY_GROUPS.get(category)
        try:
            payload = await self.service.get_nearby_poi(
                latitude=latitude,
                longitude=longitude,
                radius_m=radius_m,
                amenity_tags=amenity_tags,
                categories=categories,
                limit=_optional_int(request.params.get("limit")),
            )
        except OverpassRateLimitError as exc:
            raise ProviderRateLimitError(str(exc)) from exc
        except OverpassRequestError as exc:
            raise ProviderInvalidQueryError(str(exc)) from exc
        except (OverpassServiceError, ValueError) as exc:
            raise ProviderUnavailableError(str(exc)) from exc
        features: list[dict[str, Any]] = []
        for item in json_array(payload.get("items")):
            item = json_object(item)
            if not item:
                continue
            try:
                feature = normalize_poi_feature(
                    {
                        **item,
                        "category": item.get("amenity"),
                    },
                    source=self.provider_id,
                    category=str(item.get("amenity") or "amenity"),
                )
            except NormalizationError:
                continue
            features.append(feature.model_dump(mode="json"))
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "clustered-points",
                "features": features,
                "totalResults": len(features),
                "center": {"latitude": latitude, "longitude": longitude},
                "radiusM": radius_m,
                "resolvedAt": payload.get("resolved_at"),
            },
            attribution=[
                str(payload.get("attribution") or "© OpenStreetMap contributors (ODbL)")
            ],
            coverage={
                "type": "circle",
                "center": {"latitude": latitude, "longitude": longitude},
                "radius_m": radius_m,
            },
            spatial_resolution="point features",
            units={"distance_m": "m", "radius_m": "m"},
            source_url=getattr(self.service, "base_url", None),
            result_type="features",
            result_status="valid_empty" if not features else "ok",
        )


###############################################################################
def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except TypeError, ValueError:
        return None
