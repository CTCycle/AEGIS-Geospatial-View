from __future__ import annotations

import asyncio
import json
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
        legacy_layers = self.toolkit.normalize_layers(payload.filters)
        explicit_overlays = self.toolkit.normalize_layers(payload.overlay_ids)
        resolved = list(explicit_overlays)
        for layer in legacy_layers:
            if layer not in resolved:
                resolved.append(layer)
        return resolved

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
    ) -> dict[str, Any]:
        overlays = self.catalog_service.resolve_overlays(self._resolve_overlay_ids(payload))
        if not overlays:
            legacy_overlays = satellite_payload.get("overlays", [])
            if isinstance(legacy_overlays, list):
                for entry in legacy_overlays:
                    if not isinstance(entry, dict):
                        continue
                    overlays.append(
                        {
                            "id": str(entry.get("name") or "legacy_overlay"),
                            "label": str(entry.get("label") or "Legacy Overlay"),
                            "provider": str(entry.get("provider") or "gibs"),
                            "type": "legacy-image",
                            "default_opacity": float(entry.get("opacity", 0.68)),
                            "coverage": "dynamic",
                            "requires_key": False,
                            "attribution": entry.get("attribution"),
                        }
                    )
        basemap = self.catalog_service.resolve_basemap(payload.basemap_id)
        lat_value = self._coerce_coordinate_scalar(search_payload.get("latitude"))
        lon_value = self._coerce_coordinate_scalar(search_payload.get("longitude"))
        insights = await self.catalog_service.fetch_insights(
            latitude=lat_value,
            longitude=lon_value,
            overlay_ids=[item["id"] for item in overlays],
            radius_m=float(payload.radius_m or 2500.0),
        )
        compliance_warnings = self.catalog_service.resolve_compliance_warnings(
            basemap=basemap,
            overlays=overlays,
        )
        return {
            "center": {"latitude": lat_value, "longitude": lon_value},
            "bounds": satellite_payload.get("bbox"),
            "basemap": basemap,
            "overlays": overlays,
            "insights": insights,
            "compliance_warnings": compliance_warnings,
        }

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
        map_session = await self.assemble_map_session(
            payload=payload,
            search_payload=search_payload,
            satellite_payload=satellite_payload,
        )
        search_payload["map_session"] = map_session
        search_payload["compliance_warnings"] = map_session.get("compliance_warnings", [])

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
            "legacy_layers": layers,
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
