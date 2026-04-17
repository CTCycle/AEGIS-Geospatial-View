from __future__ import annotations

import asyncio
import json
import math
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status

from AEGIS.server.domain.geographics import LocationSearchRequest
from AEGIS.server.services.geospatial.catalog import GeospatialCatalogService
from AEGIS.server.services.geospatial.elevation import OpenElevationService
from AEGIS.server.services.geospatial.gibs import GIBSRequestError, GIBSValidationError
from AEGIS.server.services.geospatial.layers import LayerProviderError
from AEGIS.server.services.geospatial.maps import MapRequestError, MapValidationError
from AEGIS.server.services.geospatial.nominatim import NominatimService
from AEGIS.server.services.sanitization import LocationSanitizationService
from AEGIS.server.utils.constants import MAP_SEARCH_STATUS_MESSAGE
from AEGIS.server.utils.logger import logger

type CoordinatePair = tuple[float, float]


###############################################################################
class LocationSearchOrchestrator:
    def __init__(
        self,
        *,
        sanitization_service: LocationSanitizationService,
        nominatim_service: NominatimService,
        catalog_service: GeospatialCatalogService,
        elevation_service: OpenElevationService,
        renderer: Any,
        toolkit: Any,
    ) -> None:
        self.sanitization_service = sanitization_service
        self.nominatim_service = nominatim_service
        self.catalog_service = catalog_service
        self.elevation_service = elevation_service
        self.renderer = renderer
        self.toolkit = toolkit

    def _coerce_coordinate_scalar(self, value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        return None

    def _resolve_overlay_ids(self, payload: LocationSearchRequest) -> list[str]:
        explicit_overlays = self.toolkit.normalize_layers(payload.overlay_ids)
        if explicit_overlays:
            return list(explicit_overlays)
        suggest_overlay_ids = getattr(self.catalog_service, "suggest_overlay_ids_from_filters", None)
        if callable(suggest_overlay_ids):
            return self.toolkit.normalize_layers(suggest_overlay_ids(payload.semantic_filters))
        return self.toolkit.normalize_layers(payload.semantic_filters)

    def _bbox_area_degrees(self, bbox: list[float] | None) -> float:
        if not isinstance(bbox, list) or len(bbox) != 4:
            return 0.0
        try:
            minx, miny, maxx, maxy = [float(value) for value in bbox]
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, abs(maxx - minx) * abs(maxy - miny))

    def _derive_local_bbox(self, *, latitude: float, longitude: float, map_size_m: float) -> list[float]:
        half_span_m = max(250.0, float(map_size_m) / 2.0)
        deg_lat = half_span_m / 111_320.0
        cos_lat = max(0.2, math.cos(math.radians(latitude)))
        deg_lon = half_span_m / (111_320.0 * cos_lat)
        return [longitude - deg_lon, latitude - deg_lat, longitude + deg_lon, latitude + deg_lat]

    def _should_force_local_bbox(self, payload: LocationSearchRequest, nominatim_candidate: dict[str, Any]) -> bool:
        location_type = str(nominatim_candidate.get("selected_result_type") or "").lower()
        is_point_like = location_type in {"house", "building", "amenity", "attraction", "road", "residential"}
        address_like = bool(payload.address and any(char.isdigit() for char in payload.address))
        nearby_like = bool(payload.address and any(token in payload.address.lower() for token in ("nearby", "around")))
        bbox_area = self._bbox_area_degrees(nominatim_candidate.get("bbox"))
        oversized = bbox_area > 0.05
        return bool((is_point_like or address_like or nearby_like) and oversized)

    async def resolve_coordinates(self, payload: LocationSearchRequest) -> dict[str, Any]:
        response_payload = payload.model_dump()
        normalized_filters = list(payload.filters or [])
        response_payload["geospatial_filter"] = normalized_filters
        response_payload["filters"] = normalized_filters
        response_payload.pop("layers", None)
        if not payload.use_coordinates:
            sanitized_location = await asyncio.to_thread(
                self.sanitization_service.sanitize_location_inputs,
                payload.address or "",
                payload.city,
                payload.country,
            )
            response_payload["sanitized_location"] = sanitized_location
            nominatim_candidate = await self.nominatim_service.extract_coordinates(
                address=sanitized_location["address"] or "",
                city=sanitized_location["city"],
                country_name=sanitized_location["country"],
                country_code=sanitized_location["country_code"],
            )
            if nominatim_candidate:
                latitude = nominatim_candidate.get("lat")
                longitude = nominatim_candidate.get("lon")
                if latitude is not None and longitude is not None:
                    try:
                        response_payload["latitude"] = float(latitude)
                        response_payload["longitude"] = float(longitude)
                    except (TypeError, ValueError):
                        pass
                if nominatim_candidate.get("bbox"):
                    response_payload["bbox"] = nominatim_candidate["bbox"]
                if (
                    response_payload.get("latitude") is not None
                    and response_payload.get("longitude") is not None
                    and self._should_force_local_bbox(payload, nominatim_candidate)
                ):
                    response_payload["bbox"] = self._derive_local_bbox(
                        latitude=float(response_payload["latitude"]),
                        longitude=float(response_payload["longitude"]),
                        map_size_m=float(payload.map_size_m or 2500.0),
                    )
                    response_payload["bbox_source"] = "derived_local"
                if nominatim_candidate.get("confidence") is not None:
                    response_payload["confidence"] = nominatim_candidate["confidence"]
        elif payload.latitude is not None and payload.longitude is not None:
            response_payload["latitude"] = payload.latitude
            response_payload["longitude"] = payload.longitude
            bbox = await self.nominatim_service.extract_bbox_from_coordinates(
                latitude=payload.latitude,
                longitude=payload.longitude,
            )
            if bbox:
                response_payload["bbox"] = bbox
        return response_payload

    async def assemble_map_session(
        self,
        *,
        payload: LocationSearchRequest,
        search_payload: dict[str, Any],
        satellite_payload: dict[str, Any],
    ) -> tuple[dict[str, Any], list[str], list[str], list[str]]:
        selected_overlay_ids = self._resolve_overlay_ids(payload)
        unmet_filters: list[str] = []
        filter_overlay_ids = getattr(self.catalog_service, "filter_overlay_ids_by_semantics", None)
        if callable(filter_overlay_ids):
            selected_overlay_ids, unmet_filters = filter_overlay_ids(
                overlay_ids=selected_overlay_ids,
                semantic_filters=payload.semantic_filters,
            )
        overlays = self.catalog_service.resolve_overlays(selected_overlay_ids)
        basemap = self.catalog_service.resolve_basemap(payload.basemap_id)
        lat_value = self._coerce_coordinate_scalar(search_payload.get("latitude"))
        lon_value = self._coerce_coordinate_scalar(search_payload.get("longitude"))
        insights = await self.catalog_service.fetch_insights(
            latitude=lat_value,
            longitude=lon_value,
            overlay_ids=[item["id"] for item in overlays],
            radius_m=float(payload.radius_m or 2500.0),
        )
        overlay_runtime = await self.catalog_service.fetch_overlay_runtime(
            latitude=lat_value,
            longitude=lon_value,
            overlay_ids=[item["id"] for item in overlays],
            radius_m=float(payload.radius_m or 2500.0),
        )
        enriched_overlays: list[dict[str, Any]] = []
        for overlay in overlays:
            enriched = dict(overlay)
            runtime_payload = overlay_runtime.get(str(overlay.get("id")))
            if isinstance(runtime_payload, dict):
                enriched["runtime"] = runtime_payload
            else:
                enriched["runtime"] = {
                    "provider": overlay.get("provider"),
                    "resolved_timestamp": datetime.now(UTC).isoformat(),
                    "data_freshness": "unknown",
                    "availability": "unknown",
                    "error": None,
                }
            enriched_overlays.append(enriched)
        compliance_warnings = self.catalog_service.resolve_compliance_warnings(
            basemap=basemap,
            overlays=enriched_overlays,
        )
        map_session = {
            "center": {"latitude": lat_value, "longitude": lon_value},
            "bounds": satellite_payload.get("bbox"),
            "basemap": basemap,
            "overlays": enriched_overlays,
            "insights": insights,
            "compliance_warnings": compliance_warnings,
        }
        return map_session, selected_overlay_ids, payload.semantic_filters, unmet_filters

    async def execute(self, payload: LocationSearchRequest) -> dict[str, Any]:
        if payload.datetime is None:
            payload = payload.model_copy(update={"datetime": datetime.now(UTC)})
        search_payload = await self.resolve_coordinates(payload)
        lat_value = self._coerce_coordinate_scalar(search_payload.get("latitude"))
        lon_value = self._coerce_coordinate_scalar(search_payload.get("longitude"))
        bbox_value = search_payload.get("bbox")
        has_bbox = isinstance(bbox_value, list) and len(bbox_value) == 4
        if lat_value is None or lon_value is None:
            if not has_bbox:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Unable to resolve a usable location from the current request. "
                        "Please provide a more specific place or coordinates."
                    ),
                )
        try:
            satellite_payload = await self.renderer.build_satellite_payload(payload, search_payload)
        except (GIBSValidationError, MapValidationError, LayerProviderError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except (GIBSRequestError, MapRequestError) as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

        search_payload["satellite_imagery"] = satellite_payload
        map_session, selected_overlay_ids, applied_filters, unmet_filters = await self.assemble_map_session(
            payload=payload,
            search_payload=search_payload,
            satellite_payload=satellite_payload,
        )
        search_payload["map_session"] = map_session
        search_payload["compliance_warnings"] = map_session.get("compliance_warnings", [])
        search_payload["selected_overlay_ids"] = selected_overlay_ids
        search_payload["applied_filters"] = applied_filters
        search_payload["unmet_filters"] = unmet_filters
        if applied_filters and not selected_overlay_ids:
            search_payload["fallback_mode"] = "overlay_unavailable"

        if lat_value is not None and lon_value is not None:
            try:
                search_payload["elevation"] = await self.elevation_service.get_elevation(
                    lat_value, lon_value
                )
            except Exception as exc:
                logger.warning("Failed to fetch elevation: %s", exc)
                search_payload["elevation"] = None

        return {
            "status_message": MAP_SEARCH_STATUS_MESSAGE,
            "payload": search_payload,
            "map_session": map_session,
            "compliance_warnings": map_session.get("compliance_warnings", []),
        }

    def build_search_session_record(
        self,
        *,
        payload: LocationSearchRequest | None,
        response_payload: dict[str, Any] | None,
        fallback: dict[str, Any],
        state: str,
    ) -> dict[str, Any]:
        payload_snapshot = response_payload.get("payload", {}) if response_payload else {}
        coordinates: CoordinatePair | None = None
        if payload:
            coordinates = self.toolkit.extract_coordinate_pair(payload, payload_snapshot)
            if not coordinates:
                coordinates = self.toolkit.extract_coordinate_pair(payload, payload.model_dump())
        if coordinates is None:
            lon_candidate = fallback.get("longitude")
            lat_candidate = fallback.get("latitude")
            if isinstance(lon_candidate, (int, float)) and isinstance(lat_candidate, (int, float)):
                coordinates = (float(lon_candidate), float(lat_candidate))

        layers = (
            list(payload.filters)
            if payload
            else self.toolkit.normalize_layers(fallback.get("geospatial_layers") or [])
        )
        overlay_ids = (
            list(payload.overlay_ids)
            if payload
            else self.toolkit.normalize_layers(fallback.get("overlay_ids") or [])
        )
        if overlay_ids:
            layers = list(dict.fromkeys([*layers, *overlay_ids]))
        basemap_id = payload.basemap_id if payload else fallback.get("basemap_id")
        persisted_selection = {
            "filters": layers,
            "overlay_ids": overlay_ids,
            "basemap_id": basemap_id,
        }
        return {
            "id": None,
            "created_at": datetime.utcnow(),
            "user": fallback.get("user"),
            "country": payload.country if payload else fallback.get("country"),
            "city": payload.city if payload else fallback.get("city"),
            "address": payload.address if payload else fallback.get("address"),
            "coordinates": json.dumps(
                {"longitude": coordinates[0], "latitude": coordinates[1]}
            )
            if coordinates
            else None,
            "base_map": payload.map_tiles if payload else fallback.get("map_tiles"),
            "geospatial_layers": json.dumps(persisted_selection),
            "state": state,
        }
