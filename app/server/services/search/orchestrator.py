from __future__ import annotations

import math
import os
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

from server.domain.geographics import LocationSearchRequest, MapSession
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.rainviewer import (
    RainViewerRequestError,
    RainViewerService,
)


class LocationSearchOrchestrator:
    def __init__(
        self,
        *,
        capability_registry: CapabilityRegistry | None = None,
        rainviewer_service: RainViewerService | None = None,
    ) -> None:
        self.capability_registry = capability_registry or CapabilityRegistry()
        self.rainviewer_service = rainviewer_service or RainViewerService()

    async def execute(self, payload: LocationSearchRequest) -> MapSession:
        self.capability_registry.load_capabilities()
        basemap = await self._build_basemap_descriptor(payload.basemap_id)
        overlays: list[dict[str, object]] = []
        warnings: list[str] = []
        if (
            isinstance(basemap, dict)
            and basemap.get("tile_url") is None
            and basemap.get("provider") in {"tomtom", "geoapify"}
        ):
            warnings.append(
                f"{payload.basemap_id}: provider API key is required; falling back to osm_default."
            )
            basemap = await self._build_basemap_descriptor("osm_default")
        effective_basemap_id = (
            str(basemap.get("id"))
            if isinstance(basemap, dict) and basemap.get("id")
            else payload.basemap_id
        )
        for overlay_id in payload.overlay_ids:
            overlay_result = await self._build_overlay_descriptor(overlay_id, payload=payload)
            if overlay_result is None:
                warnings.append(f"Overlay '{overlay_id}' is not available in the capability catalog.")
                continue
            descriptor, overlay_warnings = overlay_result
            overlays.append(descriptor)
            warnings.extend(overlay_warnings)
        return MapSession(
            session_id=f"map-{int(datetime.now(UTC).timestamp())}",
            resolved_location=payload.resolved_location,
            basemap_id=effective_basemap_id,
            overlay_ids=list(payload.overlay_ids),
            viewport=payload.viewport,
            center={
                "latitude": payload.viewport.center_latitude,
                "longitude": payload.viewport.center_longitude,
            },
            bounds=payload.viewport.bbox or self._bounds_from_viewport(payload.viewport),
            basemap=basemap,
            overlays=overlays,
            compliance_warnings=warnings,
            payload={
                "action_id": payload.action_id,
                "time_mode": payload.time_mode,
                "presentation": payload.presentation.model_dump(mode="json"),
            },
        )

    async def _build_basemap_descriptor(self, basemap_id: str) -> dict[str, object] | None:
        capability = self.capability_registry.get_capability(basemap_id)
        if capability is None:
            return None
        metadata = self._metadata(capability)
        tile_url, _ = await self._resolve_runtime_tile_url(
            metadata.get("tile_url")
            or metadata.get("tile_url_template")
            or metadata.get("url_template")
            or metadata.get("url"),
            capability=capability,
        )
        return {
            "id": str(capability.get("id") or basemap_id),
            "label": str(metadata.get("label") or capability.get("name") or basemap_id),
            "provider": str(capability.get("provider") or "unknown"),
            "tile_url": tile_url,
            "attribution": str(metadata.get("attribution") or ""),
        }

    async def _build_overlay_descriptor(
        self, overlay_id: str, *, payload: LocationSearchRequest
    ) -> tuple[dict[str, object], list[str]] | None:
        capability = self.capability_registry.get_capability(overlay_id)
        if capability is None:
            return None
        metadata = self._metadata(capability)
        warnings: list[str] = []
        raw_url = (
            metadata.get("url_template")
            or metadata.get("tile_url_template")
            or metadata.get("tile_url")
            or metadata.get("url")
        )
        raw_url = self._apply_spatial_placeholders(raw_url, payload=payload)
        capability_type = str(capability.get("type") or "")
        rendering_mode = str(capability.get("renderingMode") or "")
        capability_kind = str(capability.get("capabilityKind") or "")
        if capability_kind == "camera-network":
            auth = capability.get("auth") if isinstance(capability.get("auth"), dict) else {}
            credential_env = self._credential_env_for_provider(
                str(auth.get("providerKey") or capability.get("provider") or "")
            )
            if bool(auth.get("required")) and credential_env and not os.getenv(credential_env, "").strip():
                warnings.append(
                    f"{overlay_id}: {credential_env} is required for live camera metadata."
                )
            camera_params = {
                "provider": str(capability.get("provider") or "unknown"),
                "bbox": self._bbox_query_value(payload),
            }
            return {
                "id": str(capability.get("id") or overlay_id),
                "label": str(metadata.get("label") or capability.get("name") or overlay_id),
                "provider": str(capability.get("provider") or "unknown"),
                "type": "camera-points",
                "rendering_mode": "camera-points",
                "url": f"/api/geospatial/cameras.geojson?{urlencode(camera_params)}",
                "attribution": str(metadata.get("attribution") or ""),
                "source_protocol": metadata.get("source_protocol"),
                "data_format": metadata.get("data_format"),
                "geometry_type": metadata.get("geometry_type"),
            }, warnings
        if (
            capability_kind in {"dataset-ingestion", "vector-overlay"}
            and rendering_mode == "vector-tile"
            and raw_url is None
        ):
            warnings.append(
                f"{overlay_id}: vector tile render metadata is incomplete; exposing metadata only."
            )
            return {
                "id": str(capability.get("id") or overlay_id),
                "label": str(metadata.get("label") or capability.get("name") or overlay_id),
                "provider": str(capability.get("provider") or "unknown"),
                "type": "metadata-only",
                "rendering_mode": "metadata-only",
                "attribution": str(metadata.get("attribution") or ""),
                "source_protocol": metadata.get("source_protocol"),
                "data_format": metadata.get("data_format"),
                "geometry_type": metadata.get("geometry_type"),
            }, warnings
        if capability_kind in {"dataset-ingestion", "vector-overlay"} and rendering_mode in {
            "clustered-points",
            "geojson",
            "choropleth",
        } and raw_url is None:
            return {
                "id": str(capability.get("id") or overlay_id),
                "label": str(metadata.get("label") or capability.get("name") or overlay_id),
                "provider": str(capability.get("provider") or "unknown"),
                "type": str(capability.get("type") or rendering_mode),
                "rendering_mode": rendering_mode,
                "url": self._feature_endpoint_url(overlay_id, payload=payload),
                "attribution": str(metadata.get("attribution") or ""),
                "source_protocol": metadata.get("source_protocol"),
                "data_format": metadata.get("data_format"),
                "geometry_type": metadata.get("geometry_type"),
            }, warnings
        is_point_insight = raw_url is None and (
            bool(capability.get("supports_direct_text"))
            or capability_type.endswith("insight")
            or rendering_mode == "metadata-only"
        )
        if is_point_insight:
            resolved_url, url_warning = None, None
        else:
            resolved_url, url_warning = await self._resolve_runtime_tile_url(
                raw_url,
                capability=capability,
            )
        if url_warning is not None:
            warnings.append(f"{overlay_id}: {url_warning}")
        descriptor: dict[str, object] = {
            "id": str(capability.get("id") or overlay_id),
            "label": str(metadata.get("label") or capability.get("name") or overlay_id),
            "provider": str(capability.get("provider") or "unknown"),
            "type": "point-insight" if is_point_insight else str(capability.get("type") or "tile"),
            "rendering_mode": rendering_mode or ("metadata-only" if is_point_insight else ""),
        }
        tile_url_template = self._build_backend_render_tile_template(
            rendering_mode=rendering_mode,
            resolved_url=resolved_url,
            metadata=metadata,
        )
        optional_fields = {
            "url": resolved_url,
            "tile_url_template": tile_url_template,
            "layers": metadata.get("layers"),
            "layer_id": metadata.get("layer_id"),
            "source_layer": metadata.get("source_layer") or metadata.get("layer_id"),
            "tile_matrix_set": metadata.get("tile_matrix_set"),
            "wmts_format": metadata.get("wmts_format"),
            "wmts_style": metadata.get("wmts_style"),
            "wms_version": metadata.get("wms_version"),
            "wms_exceptions": metadata.get("wms_exceptions"),
            "attribution": metadata.get("attribution"),
            "source_protocol": metadata.get("source_protocol"),
            "data_format": metadata.get("data_format"),
            "geometry_type": metadata.get("geometry_type"),
        }
        for key, value in optional_fields.items():
            normalized = self._optional_string(value)
            if normalized is not None:
                descriptor[key] = normalized
        if isinstance(metadata.get("default_opacity"), int | float):
            descriptor["default_opacity"] = float(metadata["default_opacity"])
        if isinstance(metadata.get("tile_size"), int | float):
            descriptor["tile_size"] = int(metadata["tile_size"])
        if isinstance(metadata.get("minzoom"), int | float):
            descriptor["minzoom"] = int(metadata["minzoom"])
        if descriptor["provider"] == "rainviewer":
            descriptor["maxzoom"] = 10
        if self._is_bounds(metadata.get("bounds")):
            descriptor["bounds"] = list(metadata["bounds"])
        return descriptor, warnings

    @staticmethod
    def _build_backend_render_tile_template(
        *,
        rendering_mode: str,
        resolved_url: str | None,
        metadata: dict[str, Any],
    ) -> str | None:
        normalized_mode = rendering_mode.lower()
        if not resolved_url:
            return None
        if normalized_mode in {"tile", "raster-tile", "xyz"}:
            return resolved_url
        if normalized_mode == "wms":
            layers = str(metadata.get("layers") or "0")
            version = str(metadata.get("wms_version") or "1.1.1")
            exceptions = str(metadata.get("wms_exceptions") or "application/vnd.ogc.se_inimage")
            separator = "&" if "?" in resolved_url else "?"
            query = "&".join(
                [
                    "service=WMS",
                    "request=GetMap",
                    f"layers={layers}",
                    "styles=",
                    "format=image/png",
                    "transparent=true",
                    f"version={version}",
                    "srs=EPSG:3857",
                    f"exceptions={exceptions}",
                    "bbox={bbox-epsg-3857}",
                    "width=256",
                    "height=256",
                ]
            )
            return f"{resolved_url}{separator}{query}"
        if normalized_mode == "wmts":
            layer_id = str(metadata.get("layer_id") or metadata.get("layers") or "layer")
            matrix_set = str(metadata.get("tile_matrix_set") or "EPSG:3857")
            fmt = str(metadata.get("wmts_format") or "image/png")
            style = str(metadata.get("wmts_style") or "")
            separator = "&" if "?" in resolved_url else "?"
            query = "&".join(
                [
                    "service=WMTS",
                    "request=GetTile",
                    "version=1.0.0",
                    f"layer={layer_id}",
                    f"style={style}",
                    f"tilematrixset={matrix_set}",
                    f"tilematrix={matrix_set}:{{z}}",
                    "tilerow={y}",
                    "tilecol={x}",
                    f"format={fmt}",
                ]
            )
            return f"{resolved_url}{separator}{query}"
        if normalized_mode == "vector-tile":
            return resolved_url
        return None

    def _apply_spatial_placeholders(
        self, value: object, *, payload: LocationSearchRequest
    ) -> object:
        template = self._optional_string(value)
        if template is None:
            return value
        bounds = payload.viewport.bbox or self._bounds_from_viewport(payload.viewport)
        if "{bbox}" in template and bounds:
            bbox = ",".join(str(round(float(item), 6)) for item in bounds)
            template = template.replace("{bbox}", bbox)
        if "{lat}" in template:
            template = template.replace("{lat}", str(payload.viewport.center_latitude))
        if "{lon}" in template:
            template = template.replace("{lon}", str(payload.viewport.center_longitude))
        return template

    def _feature_endpoint_url(
        self, overlay_id: str, *, payload: LocationSearchRequest
    ) -> str:
        params = {
            "bbox": self._bbox_query_value(payload),
            "live": "true",
        }
        return f"/api/geospatial/layers/{overlay_id}/geojson?{urlencode(params)}"

    def _bbox_query_value(self, payload: LocationSearchRequest) -> str:
        bounds = payload.viewport.bbox or self._bounds_from_viewport(payload.viewport) or []
        return ",".join(str(round(float(item), 6)) for item in bounds)

    @staticmethod
    def _metadata(capability: dict[str, Any]) -> dict[str, Any]:
        metadata = capability.get("metadata")
        return dict(metadata) if isinstance(metadata, dict) else {}

    @staticmethod
    def _optional_string(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        stripped = value.strip()
        return stripped or None

    @staticmethod
    def _bounds_from_viewport(viewport: Any) -> list[float] | None:
        latitude = getattr(viewport, "center_latitude", None)
        longitude = getattr(viewport, "center_longitude", None)
        radius_m = getattr(viewport, "radius_m", None)
        if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
            return None
        if not isinstance(radius_m, (int, float)) or radius_m <= 0:
            return None
        lat_delta = radius_m / 111_320.0
        cos_latitude = math.cos(math.radians(float(latitude)))
        lon_delta = radius_m / (111_320.0 * max(abs(cos_latitude), 0.01))
        return [
            max(-180.0, float(longitude) - lon_delta),
            max(-90.0, float(latitude) - lat_delta),
            min(180.0, float(longitude) + lon_delta),
            min(90.0, float(latitude) + lat_delta),
        ]

    async def _resolve_runtime_tile_url(
        self,
        value: object,
        *,
        capability: dict[str, Any] | None = None,
    ) -> tuple[str | None, str | None]:
        template = self._optional_string(value)
        if template is None:
            return None, "Tile URL is missing from provider metadata."
        template, credential_warning = self._resolve_credential_placeholders(
            template, capability
        )
        if credential_warning is not None:
            return None, credential_warning
        if "{time}" not in template:
            return template, None
        rainviewer_url = await self._resolve_rainviewer_tile_url()
        if rainviewer_url is not None:
            return rainviewer_url, None
        timestamp = int(datetime.now(UTC).timestamp())
        rounded_timestamp = timestamp - (timestamp % 600)
        return (
            template.replace("{time}", str(rounded_timestamp)),
            "RainViewer metadata could not be fetched; using a timestamp fallback.",
        )

    @classmethod
    def _resolve_credential_placeholders(
        cls,
        template: str,
        capability: dict[str, Any] | None,
    ) -> tuple[str, str | None]:
        if "{api_key}" not in template:
            return template, None
        provider = str((capability or {}).get("provider") or "").strip().lower()
        capability_id = str((capability or {}).get("id") or "").strip()
        env_by_provider = {
            "arcgis": "ARCGIS_API_KEY",
            "census": "CENSUS_API_KEY",
            "fred": "FRED_API_KEY",
            "tomtom": "TOMTOM_API_KEY",
            "geoapify": "GEOAPIFY_API_KEY",
            "google_maps": "GOOGLE_MAPS_API_KEY",
            "openaq": "OPENAQ_API_KEY",
        }
        env_name = env_by_provider.get(provider)
        if env_name is None:
            return template, f"No credential mapping is configured for provider '{provider}'."
        api_key = os.getenv(env_name, "").strip()
        if not api_key:
            return template, f"{env_name} is required to render this provider tile layer."
        if capability_id:
            return f"/api/geospatial/tiles/{capability_id}/{{z}}/{{x}}/{{y}}.png", None
        return template, f"Credentialed tile capability for provider '{provider}' is missing a stable id."

    @staticmethod
    def _credential_env_for_provider(provider: str) -> str | None:
        return {
            "windy_webcams": "WINDY_WEBCAMS_API_KEY",
        }.get(provider.strip().lower())

    async def _resolve_rainviewer_tile_url(self) -> str | None:
        try:
            metadata = await self.rainviewer_service.get_latest_radar_metadata()
        except RainViewerRequestError:
            return None
        tile_url = metadata.get("tile_url_template")
        if not isinstance(tile_url, str) or not tile_url.strip():
            return None
        return tile_url

    @staticmethod
    def _is_bounds(value: object) -> bool:
        return (
            isinstance(value, list)
            and len(value) == 4
            and all(isinstance(item, int | float) for item in value)
        )
