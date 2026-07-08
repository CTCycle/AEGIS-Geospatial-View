from __future__ import annotations

import math
import os
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

from server.domain.geographics import LocationSearchRequest
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.provider_registry import ProviderRegistry
from server.services.geospatial.rainviewer import RainViewerRequestError, RainViewerService

###############################################################################
class RenderDescriptorService:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        capability_registry: CapabilityRegistry | None = None,
        provider_registry: ProviderRegistry | None = None,
        rainviewer_service: RainViewerService | None = None,
    ) -> None:
        self.capability_registry = capability_registry or CapabilityRegistry()
        self.provider_registry = provider_registry or ProviderRegistry()
        self.rainviewer_service = rainviewer_service or RainViewerService()

    # -------------------------------------------------------------------------
    async def build_basemap_descriptor(self, basemap_id: str) -> dict[str, object] | None:
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

    # -------------------------------------------------------------------------
    async def build_overlay_descriptor(
        self, overlay_id: str, *, request: LocationSearchRequest
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
        raw_url = self._apply_spatial_placeholders(raw_url, request=request)
        capability_type = str(capability.get("type") or "")
        rendering_mode = str(capability.get("renderingMode") or "")
        capability_kind = str(capability.get("capabilityKind") or "")
        if capability_kind == "camera-network":
            auth = capability.get("auth") if isinstance(capability.get("auth"), dict) else {}
            credential_env = self._credential_env_for_provider(
                str(auth.get("providerKey") or capability.get("provider") or "")
            )
            if bool(auth.get("required")) and credential_env and not os.getenv(credential_env, "").strip():
                warnings.append(f"{overlay_id}: {credential_env} is required for live camera metadata.")
            camera_params = {
                "provider": str(capability.get("provider") or "unknown"),
                "bbox": self._bbox_query_value(request),
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
            and rendering_mode in {"clustered-points", "geojson", "choropleth"}
            and raw_url is None
        ):
            return self._feature_overlay_descriptor(capability, metadata, overlay_id, request), warnings
        if capability_kind in {"dataset-ingestion", "vector-overlay"} and rendering_mode == "vector-tile" and raw_url is None:
            warnings.append(f"{overlay_id}: vector tile render metadata is incomplete; exposing metadata only.")
            return self.metadata_only_descriptor(capability, metadata, overlay_id), warnings
        is_point_insight = raw_url is None and (
            bool(capability.get("supports_direct_text"))
            or capability_type.endswith("insight")
            or rendering_mode == "metadata-only"
        )
        resolved_url, url_warning = (None, None) if is_point_insight else await self._resolve_runtime_tile_url(raw_url, capability=capability)
        if url_warning is not None:
            warnings.append(f"{overlay_id}: {url_warning}")
        descriptor = self._base_overlay_descriptor(
            capability,
            metadata,
            overlay_id,
            "point-insight" if is_point_insight else str(capability.get("type") or "tile"),
            rendering_mode or ("metadata-only" if is_point_insight else ""),
        )
        render = self._build_render_descriptor(rendering_mode, resolved_url, metadata)
        if resolved_url is not None:
            descriptor["url"] = resolved_url
        if render is not None:
            descriptor["render"] = render
            tile_url_template = render.get("tile_url_template")
            if tile_url_template is not None:
                descriptor["tile_url_template"] = tile_url_template
        for key in (
            "layers",
            "layer_id",
            "source_layer",
            "tile_matrix_set",
            "attribution",
            "source_protocol",
            "data_format",
            "geometry_type",
            "time",
            "default_time",
            "format",
            "style",
        ):
            value = metadata.get(key)
            if key == "source_layer":
                value = value or metadata.get("layer_id")
            normalized = self._optional_string(value)
            if normalized is not None:
                descriptor[key] = normalized
        for key in ("default_opacity", "tile_size", "minzoom", "maxzoom"):
            if isinstance(metadata.get(key), int | float):
                descriptor[key] = int(metadata[key]) if key != "default_opacity" else float(metadata[key])
        if descriptor["provider"] == "rainviewer":
            descriptor["maxzoom"] = 10
        if self._is_bounds(metadata.get("bounds")):
            descriptor["bounds"] = list(metadata["bounds"])
        return descriptor, warnings

    # -------------------------------------------------------------------------
    async def build_provider_layer_overlay(
        self,
        *,
        provider_id: str,
        layer_id: str,
        request: LocationSearchRequest,
        refresh: bool = False,
    ) -> tuple[dict[str, object], list[str]]:
        self.provider_registry.build_from_manifests()
        layer = await self.provider_registry.describe_layer(provider_id, layer_id, refresh=refresh)
        render = layer.render
        render_payload = render.model_dump(mode="json") if render else None
        requested_time = self._optional_string(getattr(request, "time", None))
        if render_payload is not None and requested_time:
            render_payload["time"] = requested_time
            if render_payload.get("tile_url_template"):
                render_payload["tile_url_template"] = str(render_payload["tile_url_template"]).replace("{time}", requested_time)
        descriptor: dict[str, object] = {
            "id": f"{provider_id}:{layer.layer_id}",
            "label": layer.title,
            "provider": provider_id,
            "type": "raster-overlay" if render else "metadata-only",
            "rendering_mode": render.rendering_mode if render else "metadata-only",
            "render": render_payload,
            "url": render.url if render else None,
            "tile_url_template": render_payload.get("tile_url_template") if isinstance(render_payload, dict) else None,
            "layer_id": layer.layer_id,
            "time": requested_time if requested_time else layer.default_time,
            "default_time": layer.default_time,
            "attribution": "; ".join(layer.attribution),
            "source_protocol": layer.source_protocol,
            "data_format": layer.data_format,
            "geometry_type": layer.geometry_type,
            "warnings": list(layer.warnings),
        }
        return descriptor, list(layer.warnings)

    # -------------------------------------------------------------------------
    def _build_render_descriptor(
        self,
        rendering_mode: str,
        resolved_url: str | None,
        metadata: dict[str, Any],
    ) -> dict[str, object] | None:
        normalized_mode = rendering_mode.lower()
        if not resolved_url:
            return None
        if normalized_mode in {"tile", "raster-tile", "xyz", "vector-tile"}:
            return {
                "provider": str(metadata.get("provider") or ""),
                "layer_id": str(metadata.get("layer_id") or metadata.get("layers") or ""),
                "rendering_mode": normalized_mode,
                "source_protocol": str(metadata.get("source_protocol") or normalized_mode),
                "tile_url_template": resolved_url,
                "attribution": [str(metadata.get("attribution") or "")],
            }
        if normalized_mode == "wms":
            layer_id = str(metadata.get("layer_id") or metadata.get("layers") or "0")
            crs = str(metadata.get("crs") or "EPSG:3857")
            image_format = str(metadata.get("format") or metadata.get("wms_format") or "image/png")
            return {
                "provider": str(metadata.get("provider") or ""),
                "layer_id": layer_id,
                "rendering_mode": "wms",
                "source_protocol": "wms",
                "url": resolved_url,
                "tile_url_template": self.build_wms_tile_template(
                    url=resolved_url,
                    layer_id=layer_id,
                    crs=crs,
                    image_format=image_format,
                    style=str(metadata.get("style") or ""),
                    time=str(metadata.get("time") or metadata.get("default_time") or ""),
                    version=str(metadata.get("wms_version") or "1.1.1"),
                    exceptions=str(metadata.get("wms_exceptions") or "application/vnd.ogc.se_inimage"),
                ),
                "crs": crs,
                "format": image_format,
                "style": str(metadata.get("style") or ""),
                "time": metadata.get("time"),
                "default_time": metadata.get("default_time"),
                "attribution": [str(metadata.get("attribution") or "")],
            }
        if normalized_mode == "wmts":
            layer_id = str(metadata.get("layer_id") or metadata.get("layers") or "layer")
            matrix_set = str(metadata.get("tile_matrix_set") or "EPSG:3857")
            image_format = str(metadata.get("format") or metadata.get("wmts_format") or "image/png")
            style = str(metadata.get("style") or metadata.get("wmts_style") or "default")
            return {
                "provider": str(metadata.get("provider") or ""),
                "layer_id": layer_id,
                "rendering_mode": "wmts",
                "source_protocol": "wmts",
                "url": resolved_url,
                "tile_url_template": self.build_wmts_tile_template(
                    url=resolved_url,
                    layer_id=layer_id,
                    style=style,
                    image_format=image_format,
                    tile_matrix_set=matrix_set,
                    time=str(metadata.get("time") or metadata.get("default_time") or ""),
                ),
                "format": image_format,
                "style": style,
                "tile_matrix_set": matrix_set,
                "time": metadata.get("time"),
                "default_time": metadata.get("default_time"),
                "attribution": [str(metadata.get("attribution") or "")],
            }
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def build_wms_tile_template(
        *,
        url: str,
        layer_id: str,
        crs: str,
        image_format: str,
        style: str,
        time: str,
        version: str,
        exceptions: str,
    ) -> str:
        crs_key = "crs" if version.startswith("1.3") else "srs"
        query = [
            "service=WMS",
            "request=GetMap",
            f"layers={layer_id}",
            f"styles={style}",
            f"format={image_format}",
            "transparent=true",
            f"version={version}",
            f"{crs_key}={crs}",
            f"exceptions={exceptions}",
            "bbox={bbox-epsg-3857}",
            "width=256",
            "height=256",
        ]
        if time:
            query.append(f"time={time}")
        return f"{url}{'&' if '?' in url else '?'}{'&'.join(query)}"

    # -------------------------------------------------------------------------
    @staticmethod
    def build_wmts_tile_template(
        *,
        url: str,
        layer_id: str,
        style: str,
        image_format: str,
        tile_matrix_set: str,
        time: str,
    ) -> str:
        query = [
            "service=WMTS",
            "request=GetTile",
            "version=1.0.0",
            f"layer={layer_id}",
            f"style={style}",
            f"tilematrixset={tile_matrix_set}",
            f"tilematrix={tile_matrix_set}:{{z}}",
            "tilerow={y}",
            "tilecol={x}",
            f"format={image_format}",
        ]
        if time:
            query.append(f"time={time}")
        return f"{url}{'&' if '?' in url else '?'}{'&'.join(query)}"

    # -------------------------------------------------------------------------
    def metadata_only_descriptor(
        self,
        capability: dict[str, Any],
        metadata: dict[str, Any],
        overlay_id: str,
    ) -> dict[str, object]:
        return self._base_overlay_descriptor(capability, metadata, overlay_id, "metadata-only", "metadata-only")

    # -------------------------------------------------------------------------
    def _feature_overlay_descriptor(
        self,
        capability: dict[str, Any],
        metadata: dict[str, Any],
        overlay_id: str,
        request: LocationSearchRequest,
    ) -> dict[str, object]:
        rendering_mode = str(capability.get("renderingMode") or "")
        descriptor = self._base_overlay_descriptor(
            capability,
            metadata,
            overlay_id,
            str(capability.get("type") or rendering_mode),
            rendering_mode,
        )
        descriptor["url"] = self._feature_endpoint_url(overlay_id, request=request)
        return descriptor

    # -------------------------------------------------------------------------
    @staticmethod
    def _base_overlay_descriptor(
        capability: dict[str, Any],
        metadata: dict[str, Any],
        overlay_id: str,
        overlay_type: str,
        rendering_mode: str,
    ) -> dict[str, object]:
        return {
            "id": str(capability.get("id") or overlay_id),
            "label": str(metadata.get("label") or capability.get("name") or overlay_id),
            "provider": str(capability.get("provider") or "unknown"),
            "type": overlay_type,
            "rendering_mode": rendering_mode,
            "attribution": str(metadata.get("attribution") or ""),
            "source_protocol": metadata.get("source_protocol"),
            "data_format": metadata.get("data_format"),
            "geometry_type": metadata.get("geometry_type"),
        }

    # -------------------------------------------------------------------------
    def _apply_spatial_placeholders(self, value: object, *, request: LocationSearchRequest) -> object:
        template = self._optional_string(value)
        if template is None:
            return value
        bounds = request.viewport.bbox or self._bounds_from_viewport(request.viewport)
        if "{bbox}" in template and bounds:
            bbox = ",".join(str(round(float(item), 6)) for item in bounds)
            template = template.replace("{bbox}", bbox)
        if "{lat}" in template:
            template = template.replace("{lat}", str(request.viewport.center_latitude))
        if "{lon}" in template:
            template = template.replace("{lon}", str(request.viewport.center_longitude))
        return template

    # -------------------------------------------------------------------------
    def _feature_endpoint_url(self, overlay_id: str, *, request: LocationSearchRequest) -> str:
        return f"/api/geospatial/layers/{overlay_id}/geojson?{urlencode({'bbox': self._bbox_query_value(request), 'live': 'true'})}"

    # -------------------------------------------------------------------------
    def _bbox_query_value(self, request: LocationSearchRequest) -> str:
        bounds = request.viewport.bbox or self._bounds_from_viewport(request.viewport) or []
        return ",".join(str(round(float(item), 6)) for item in bounds)

    # -------------------------------------------------------------------------
    async def _resolve_runtime_tile_url(
        self,
        value: object,
        *,
        capability: dict[str, Any] | None = None,
    ) -> tuple[str | None, str | None]:
        template = self._optional_string(value)
        if template is None:
            return None, "Tile URL is missing from provider metadata."
        template, credential_warning = self._resolve_credential_placeholders(template, capability)
        if credential_warning is not None:
            return None, credential_warning
        if "{time}" not in template:
            return template, None
        rainviewer_url = await self._resolve_rainviewer_tile_url()
        if rainviewer_url is not None:
            return rainviewer_url, None
        timestamp = int(datetime.now(UTC).timestamp())
        rounded_timestamp = timestamp - (timestamp % 600)
        return template.replace("{time}", str(rounded_timestamp)), "RainViewer metadata could not be fetched; using a timestamp fallback."

    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    @staticmethod
    def _metadata(capability: dict[str, Any]) -> dict[str, Any]:
        metadata = capability.get("metadata")
        return dict(metadata) if isinstance(metadata, dict) else {}

    # -------------------------------------------------------------------------
    @staticmethod
    def _optional_string(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        stripped = value.strip()
        return stripped or None

    # -------------------------------------------------------------------------
    @staticmethod
    def _credential_env_for_provider(provider: str) -> str | None:
        return {"windy_webcams": "WINDY_WEBCAMS_API_KEY"}.get(provider.strip().lower())

    # -------------------------------------------------------------------------
    async def _resolve_rainviewer_tile_url(self) -> str | None:
        try:
            metadata = await self.rainviewer_service.get_latest_radar_metadata()
        except RainViewerRequestError:
            return None
        tile_url = metadata.get("tile_url_template")
        if not isinstance(tile_url, str) or not tile_url.strip():
            return None
        return tile_url

    # -------------------------------------------------------------------------
    @staticmethod
    def _is_bounds(value: object) -> bool:
        return isinstance(value, list) and len(value) == 4 and all(isinstance(item, int | float) for item in value)

    # -------------------------------------------------------------------------
    @staticmethod
    def _bounds_from_viewport(viewport: Any) -> list[float] | None:
        latitude = getattr(viewport, "center_latitude", None)
        longitude = getattr(viewport, "center_longitude", None)
        radius_m = getattr(viewport, "radius_m", None)
        if not isinstance(latitude, int | float) or not isinstance(longitude, int | float):
            return None
        if not isinstance(radius_m, int | float) or radius_m <= 0:
            return None
        lat_delta = radius_m / 111_320.0
        lon_delta = radius_m / (111_320.0 * max(abs(math.cos(math.radians(float(latitude)))), 0.01))
        return [
            max(-180.0, float(longitude) - lon_delta),
            max(-90.0, float(latitude) - lat_delta),
            min(180.0, float(longitude) + lon_delta),
            min(90.0, float(latitude) + lat_delta),
        ]
