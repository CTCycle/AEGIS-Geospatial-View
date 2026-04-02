from __future__ import annotations

import asyncio
import base64
import json
from datetime import datetime, time
from io import BytesIO
from typing import Any, Mapping, Sequence

from fastapi import APIRouter, Body, HTTPException, status
from PIL import Image
from pydantic import ValidationError

from AEGIS.server.utils.constants import (
    JOB_STATUS_CANCELLED,
    MAP_SEARCH_CANCELLATION_NOT_ALLOWED,
    MAP_SEARCH_CANCELLATION_REQUESTED,
    MAP_SEARCH_JOB_INIT_ERROR,
    MAP_SEARCH_JOB_PROGRESS_COORDINATES,
    MAP_SEARCH_JOB_PROGRESS_IMAGERY,
    MAP_SEARCH_JOB_PROGRESS_PERSISTED,
    MAP_SEARCH_JOB_PROGRESS_POSTPROCESS,
    MAP_SEARCH_JOB_START_MESSAGE,
    MAP_SEARCH_STATUS_MESSAGE,
    MAPS_CATALOG_ROUTE,
    MAPS_JOB_ROUTE,
    MAPS_JOBS_ROUTE,
    MAPS_ROUTER_PREFIX,
    MAPS_SEARCH_ROUTE,
)
from AEGIS.server.domain.geographics import (
    GeospatialCatalogResponse,
    LocationSearchRequest,
    SearchByLocationResponse,
)
from AEGIS.server.domain.jobs import (
    JobCancelResponse,
    JobStartResponse,
    JobStatusResponse,
)
from AEGIS.server.configurations import server_settings
from AEGIS.server.services.jobs import JobManager, job_manager
from AEGIS.server.services.search.factory import (
    build_location_search_payload_data,
    build_request_context,
    build_search_response,
)
from AEGIS.server.utils.logger import logger
from AEGIS.server.repositories.serialization import DataSerializer
from AEGIS.server.services.geospatial.gibs import (
    GIBSRequestError,
    GIBSService,
    GIBSValidationError,
)
from AEGIS.server.services.geospatial.elevation import OpenElevationService
from AEGIS.server.services.geospatial.openaq import OpenAQService
from AEGIS.server.services.geospatial.pvgis import PVGISService
from AEGIS.server.services.geospatial.catalog import GeospatialCatalogService
from AEGIS.server.services.geospatial.layers import (
    LayerProviderError,
    LayerProviderEntry,
    LayerProviderService,
)
from AEGIS.server.services.geospatial.maps import (
    MapRequestError,
    MapService,
    MapValidationError,
)
from AEGIS.server.services.geospatial.normatim import NormatimService
from AEGIS.server.services.sanitization import LocationSanitizationService

router = APIRouter(prefix=MAPS_ROUTER_PREFIX, tags=["search"])

sanitization_service = LocationSanitizationService()
normatim_service = NormatimService()
gibs_service = GIBSService()
map_service = MapService()
layer_service = LayerProviderService(
    metadata_provider=gibs_service.resolve_layer_meters_per_pixel
)
elevation_service = OpenElevationService()
openaq_service = OpenAQService()
pvgis_service = PVGISService()
catalog_service = GeospatialCatalogService(
    openaq_service=openaq_service,
    pvgis_service=pvgis_service,
)

type CoordinatePair = tuple[float, float]
DEFAULT_OVERLAY_COLOR = "#2563eb"


# -------------------------------------------------------------------------
def sanitize_validation_errors(
    errors: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for error in errors:
        normalized = dict(error)
        context = normalized.get("ctx")
        if isinstance(context, dict):
            normalized["ctx"] = {key: str(value) for key, value in context.items()}
        sanitized.append(normalized)
    return sanitized


###############################################################################
def run_map_search_job(
    endpoint: "MapSearchEndpoint",
    payload: LocationSearchRequest,
    request_context: dict[str, Any],
    job_id: str,
) -> dict[str, Any]:
    return asyncio.run(
        endpoint.process_location_search_job(
            payload=payload,
            request_context=request_context,
            job_id=job_id,
        )
    )


###############################################################################
class MapSearchToolkit:
    def __init__(self, gibs_service: GIBSService, *, default_layer: str) -> None:
        self.gibs_service = gibs_service
        self.default_layer = default_layer

    # -------------------------------------------------------------------------
    def select_primary_layer(self, layers: list[str]) -> str | None:
        if not isinstance(layers, list):
            return None
        for value in layers:
            normalized = str(value).strip()
            if normalized and normalized.lower() != "none":
                return normalized
        return None

    # -------------------------------------------------------------------------
    def normalize_layer_value(self, value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized or normalized.lower() == "none":
            return None
        return normalized

    # -------------------------------------------------------------------------
    def normalize_layers(self, layers: list[str] | tuple[str, ...] | None) -> list[str]:
        if layers is None:
            return []
        normalized: list[str] = []
        for candidate in layers:
            layer_value = self.normalize_layer_value(candidate)
            if layer_value is None or layer_value in normalized:
                continue
            normalized.append(layer_value)
        return normalized

    # -------------------------------------------------------------------------
    def merge_layer_selections(
        self,
        base_layers: list[str],
        *,
        additions: list[str] | None = None,
        removals: list[str] | None = None,
        override_layers: list[str] | None = None,
    ) -> list[str]:
        if override_layers is not None:
            return list(override_layers)
        merged = list(base_layers)
        for entry in self.normalize_layers(additions or []):
            if entry not in merged:
                merged.append(entry)
        removal_values = {
            value.lower() for value in self.normalize_layers(removals or [])
        }
        if removal_values:
            merged = [value for value in merged if value.lower() not in removal_values]
        return merged

    # -------------------------------------------------------------------------
    def resolve_imagery_date(self, payload: LocationSearchRequest) -> str:
        if payload.datetime:
            return payload.datetime.date().isoformat()
        raise GIBSValidationError("Provide datetime to determine imagery date.")

    # -------------------------------------------------------------------------
    def resolve_imagery_layer(self, payload: LocationSearchRequest) -> str:
        selected_layer = self.select_primary_layer(payload.filters)
        return selected_layer or self.default_layer

    # -------------------------------------------------------------------------
    def extract_coordinate_pair(
        self, payload: LocationSearchRequest, response_payload: dict[str, Any]
    ) -> CoordinatePair | None:
        lat_value = payload.latitude
        lon_value = payload.longitude
        if lat_value is not None and lon_value is not None:
            return lon_value, lat_value
        coordinates = response_payload.get("coordinates")
        if isinstance(coordinates, dict):
            lat_candidate = coordinates.get("latitude")
            lon_candidate = coordinates.get("longitude")
            if isinstance(lat_candidate, (int, float)) and isinstance(
                lon_candidate, (int, float)
            ):
                return float(lon_candidate), float(lat_candidate)
        lat_literal = response_payload.get("latitude")
        lon_literal = response_payload.get("longitude")
        if isinstance(lat_literal, (int, float)) and isinstance(
            lon_literal, (int, float)
        ):
            return float(lon_literal), float(lat_literal)
        return None

    # -------------------------------------------------------------------------
    def parse_bbox_values(self, candidate: Any) -> list[float] | None:
        if isinstance(candidate, (list, tuple)) and len(candidate) == 4:
            parsed: list[float] = []
            try:
                for value in candidate:
                    parsed.append(float(value))
            except (TypeError, ValueError):
                return None
            return parsed
        return None

    # -------------------------------------------------------------------------
    def resolve_bbox_candidate(
        self, payload: LocationSearchRequest, response_payload: dict[str, Any]
    ) -> tuple[list[float] | None, str | None]:
        if payload.bbox:
            normalized = self.parse_bbox_values(payload.bbox)
            if normalized:
                return normalized, payload.image_crs
        inherited = self.parse_bbox_values(response_payload.get("bbox"))
        if inherited:
            return inherited, "EPSG:4326"
        return None, None

    # -------------------------------------------------------------------------
    def harmonize_bbox_crs(
        self, bbox: list[float] | None, *, source_crs: str | None, target_crs: str
    ) -> list[float] | None:
        if bbox is None:
            return None
        target = (target_crs or "").upper()
        if not target:
            raise GIBSValidationError("Satellite imagery CRS is required.")
        source = (source_crs or target).upper()
        if source == target:
            return bbox
        supported = {"EPSG:4326", "EPSG:3857"}
        if source not in supported or target not in supported:
            raise GIBSValidationError(
                f"Unsupported bbox reprojection from {source} to {target}."
            )
        return self.gibs_service.reproject_bbox(bbox, target)

    # -------------------------------------------------------------------------
    def resolve_imagery_bbox(
        self,
        bbox: list[float] | None,
        *,
        source_crs: str | None,
        target_crs: str,
        coordinates: CoordinatePair | None,
        radius_m: float,
    ) -> list[float] | None:
        normalized = self.harmonize_bbox_crs(
            bbox,
            source_crs=source_crs,
            target_crs=target_crs,
        )
        if normalized:
            return normalized
        if coordinates is None:
            return None
        lon, lat = coordinates
        return self.gibs_service.normalize_bbox(
            bbox=None,
            lon=lon,
            lat=lat,
            radius_m=radius_m,
            target_crs=target_crs,
        )

    # -------------------------------------------------------------------------
    def encode_image(self, data: bytes) -> str:
        if not data:
            return ""
        return base64.b64encode(data).decode("ascii")


###############################################################################
class MapRenderingService:
    def __init__(
        self,
        toolkit: MapSearchToolkit,
        map_service: MapService,
        gibs_service: GIBSService,
        layer_service: LayerProviderService,
    ) -> None:
        self.toolkit = toolkit
        self.map_service = map_service
        self.gibs_service = gibs_service
        self.layer_service = layer_service

    # -------------------------------------------------------------------------
    async def build_satellite_payload(
        self,
        payload: LocationSearchRequest,
        response_payload: dict[str, Any],
    ) -> dict[str, Any]:
        coordinate_pair = self.toolkit.extract_coordinate_pair(
            payload, response_payload
        )
        bbox_candidate, bbox_source_crs = self.toolkit.resolve_bbox_candidate(
            payload, response_payload
        )
        map_bbox = self._derive_map_bbox(
            bbox_candidate=bbox_candidate,
            bbox_source_crs=bbox_source_crs,
            coordinates=coordinate_pair,
            payload=payload,
        )
        if map_bbox is None:
            raise MapValidationError(
                "Unable to resolve map extent for the requested imagery."
            )
        # Preserve the original map bbox for the view (fit_bounds).
        # Expand a separate bbox for overlay fetching and positioning.
        view_bbox = list(map_bbox)
        overlay_layers = self.toolkit.normalize_layers(payload.filters)
        overlay_bbox = self._expand_map_bbox_for_layers(
            map_bbox=list(map_bbox),
            overlay_layers=overlay_layers,
            payload=payload,
        )
        (
            span_x_m,
            span_y_m,
            meters_per_pixel,
            pixels_per_meter,
        ) = self._compute_map_metrics(map_bbox=overlay_bbox, payload=payload)
        imagery_bbox = self.toolkit.harmonize_bbox_crs(
            overlay_bbox,
            source_crs="EPSG:4326",
            target_crs=payload.image_crs,
        )
        if imagery_bbox is None:
            raise GIBSValidationError(
                "Unable to project map extent to requested imagery CRS."
            )
        overlays = await self._render_layer_overlays(
            payload=payload,
            overlay_layers=overlay_layers,
            map_bbox=overlay_bbox,
            imagery_bbox=imagery_bbox,
            span_x_m=span_x_m,
            span_y_m=span_y_m,
            map_meters_per_pixel=meters_per_pixel,
            pixels_per_meter=pixels_per_meter,
        )
        # Use view_bbox for fit_bounds (preserves zoom) but overlay_bbox for overlays
        map_response = await self._render_base_map(
            payload=payload,
            coordinate_pair=coordinate_pair,
            bbox=view_bbox,
            overlays=overlays,
        )
        if overlays:
            map_response["overlays"] = [
                self._prepare_overlay_response(entry) for entry in overlays
            ]
        map_response["meters_per_pixel"] = meters_per_pixel
        map_response["pixels_per_meter"] = pixels_per_meter
        primary_layer = self.toolkit.resolve_imagery_layer(payload)
        try:
            primary_entry = self.layer_service.resolve(primary_layer)
            map_response["layer"] = primary_entry.name
            map_response["layer_label"] = primary_entry.label
            map_response["layer_resolution_m"] = primary_entry.resolution_m
        except LayerProviderError:
            map_response["layer"] = primary_layer
            map_response["layer_label"] = primary_layer
            map_response["layer_resolution_m"] = None
        map_response["date"] = self.toolkit.resolve_imagery_date(payload)
        return map_response

    # -------------------------------------------------------------------------
    async def _render_base_map(
        self,
        *,
        payload: LocationSearchRequest,
        coordinate_pair: CoordinatePair | None,
        bbox: list[float] | None,
        overlays: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        if not bbox and not coordinate_pair:
            raise MapValidationError(
                "Provide coordinates or bbox for satellite imagery requests."
            )
        lon = coordinate_pair[0] if coordinate_pair else None
        lat = coordinate_pair[1] if coordinate_pair else None
        map_size_value = payload.map_size_m or server_settings.map.default_size_m
        map_arguments = {
            "lon": lon,
            "lat": lat,
            "bbox": bbox,
            "map_size_m": map_size_value,
            "width": payload.image_width,
            "height": payload.image_height,
            "tiles": payload.map_tiles,
            "overlays": overlays,
        }
        map_response = await asyncio.to_thread(
            self.map_service.fetch_map_image, **map_arguments
        )
        image_bytes = map_response.pop("image_bytes", b"")
        map_response["image_base64"] = self.toolkit.encode_image(image_bytes)
        map_response["mime"] = map_response.get("mime", payload.image_format)
        return map_response

    # -------------------------------------------------------------------------
    def _expand_map_bbox_for_layers(
        self,
        *,
        map_bbox: list[float],
        overlay_layers: list[str],
        payload: LocationSearchRequest,
    ) -> list[float]:
        # Expand bbox to ensure overlay layers have enough area to cover given
        # their native resolution. This expanded bbox is used for overlay
        # fetching/positioning while the original bbox is used for map view.
        if not overlay_layers:
            return map_bbox
        resolutions: list[float] = []
        for layer_name in overlay_layers:
            try:
                entry = self.layer_service.resolve(layer_name)
                if entry.resolution_m:
                    resolutions.append(entry.resolution_m)
            except LayerProviderError:
                continue
        if not resolutions:
            return map_bbox
        target_resolution = max(resolutions)
        target_span_x = target_resolution * float(payload.image_width)
        target_span_y = target_resolution * float(payload.image_height)
        span_x, span_y = self.gibs_service.bbox_span_in_meters(map_bbox, "EPSG:4326")
        if span_x >= target_span_x and span_y >= target_span_y:
            return map_bbox
        try:
            return self.gibs_service.expand_bbox_to_span(
                map_bbox, "EPSG:4326", target_span_x, target_span_y
            )
        except GIBSValidationError:
            return map_bbox

    # -------------------------------------------------------------------------
    async def _render_layer_overlays(
        self,
        *,
        payload: LocationSearchRequest,
        overlay_layers: list[str],
        map_bbox: list[float] | None,
        imagery_bbox: list[float] | None,
        span_x_m: float,
        span_y_m: float,
        map_meters_per_pixel: dict[str, float] | None,
        pixels_per_meter: dict[str, float],
    ) -> list[dict[str, Any]]:
        normalized_layers = overlay_layers
        if not normalized_layers:
            return []
        if map_bbox is None or imagery_bbox is None:
            raise GIBSValidationError(
                "Provide bbox to render geospatial overlay layers."
            )
        overlays: list[dict[str, Any]] = []
        imagery_date = self.toolkit.resolve_imagery_date(payload)
        map_bounds = self._bbox_to_bounds(map_bbox)
        for index, layer_name in enumerate(normalized_layers):
            layer_entry = self.layer_service.resolve(layer_name)
            layer_payload = await self._fetch_overlay_for_entry(
                entry=layer_entry,
                lon=None,
                lat=None,
                bbox=imagery_bbox,
                payload=payload,
                imagery_date=imagery_date,
            )
            if self._should_render_as_fill(
                resolution_m=layer_entry.resolution_m,
                span_x_m=span_x_m,
                span_y_m=span_y_m,
                overlay_meters_per_pixel=layer_payload.get("meters_per_pixel"),
                map_meters_per_pixel=map_meters_per_pixel,
            ):
                overlays.append(
                    self._build_fill_overlay(
                        entry=layer_entry,
                        bounds=map_bounds,
                        index=index,
                        pixels_per_meter=pixels_per_meter,
                        fill_color=self._derive_heatmap_color(
                            layer_payload.get("image_bytes")
                        ),
                    )
                )
                continue
            overlays.append(
                self._build_image_overlay(
                    entry=layer_entry,
                    payload=layer_payload,
                    fallback_bounds=map_bounds,
                    index=index,
                )
            )
        return overlays

    # -------------------------------------------------------------------------
    async def _fetch_overlay_for_entry(
        self,
        *,
        entry: LayerProviderEntry,
        lon: float | None,
        lat: float | None,
        bbox: list[float] | None,
        payload: LocationSearchRequest,
        imagery_date: str,
    ) -> dict[str, Any]:
        if entry.provider == "gibs":
            return await asyncio.to_thread(
                self.gibs_service.fetch_image,
                lon=lon,
                lat=lat,
                bbox=bbox,
                radius_m=payload.radius_m,
                date=imagery_date,
                layer=entry.provider_name or entry.name,
                width=payload.image_width,
                height=payload.image_height,
                crs=payload.image_crs,
                format=payload.image_format,
                skip_bbox_expansion=True,
            )
        raise LayerProviderError(
            f"No imagery service registered for provider '{entry.provider}'."
        )

    # -------------------------------------------------------------------------
    def _derive_map_bbox(
        self,
        *,
        bbox_candidate: list[float] | None,
        bbox_source_crs: str | None,
        coordinates: CoordinatePair | None,
        payload: LocationSearchRequest,
    ) -> list[float] | None:
        # Always compute bbox from coordinates + map_size_m to ensure consistent
        # sizing between map view and overlays. The geocoding bbox can be very
        # small (e.g., 30m for a specific street address), which causes overlays
        # to appear as tiny squares when the map is rendered at a larger scale.
        if coordinates is not None:
            lon, lat = coordinates
            map_size_value = payload.map_size_m or server_settings.map.default_size_m
            return self.map_service.compute_bbox_from_center(lon, lat, map_size_value)
        # Fall back to provided bbox if no coordinates available
        harmonized = self.toolkit.harmonize_bbox_crs(
            bbox_candidate,
            source_crs=bbox_source_crs,
            target_crs="EPSG:4326",
        )
        if harmonized:
            return harmonized
        return None

    # -------------------------------------------------------------------------
    def _compute_map_metrics(
        self,
        *,
        map_bbox: list[float],
        payload: LocationSearchRequest,
    ) -> tuple[
        float,
        float,
        dict[str, float],
        dict[str, float],
    ]:
        span_x_m, span_y_m = self.gibs_service.bbox_span_in_meters(
            map_bbox, "EPSG:4326"
        )
        meters_per_pixel = self.gibs_service.compute_meters_per_pixel(
            map_bbox,
            "EPSG:4326",
            payload.image_width,
            payload.image_height,
        )
        pixels_per_meter = self._compute_pixels_from_meters(meters_per_pixel)
        return span_x_m, span_y_m, meters_per_pixel, pixels_per_meter

    # -------------------------------------------------------------------------
    def _compute_pixels_from_meters(
        self, meters_per_pixel: dict[str, float] | None
    ) -> dict[str, float]:
        if not meters_per_pixel:
            return {"x": 0.0, "y": 0.0}
        metrics: dict[str, float] = {}
        for axis in ("x", "y"):
            value = float(meters_per_pixel.get(axis, 0.0))
            metrics[axis] = 0.0 if value <= 0 else 1.0 / value
        return metrics

    # -------------------------------------------------------------------------
    def _derive_heatmap_color(self, image_bytes: bytes | None) -> str:
        if not image_bytes:
            return DEFAULT_OVERLAY_COLOR
        try:
            with Image.open(BytesIO(image_bytes)) as image:
                sample_size = (
                    min(image.width, 64) or 1,
                    min(image.height, 64) or 1,
                )
                sample = image.resize(sample_size).convert("RGBA")
                data = sample.getdata()
                total_r = total_g = total_b = count = 0
                for pixel in data:
                    if not isinstance(pixel, tuple) or len(pixel) < 4:
                        continue
                    red, green, blue, alpha = pixel[:4]
                    if alpha <= 5:
                        continue
                    total_r += red
                    total_g += green
                    total_b += blue
                    count += 1
                if count == 0:
                    return DEFAULT_OVERLAY_COLOR
                avg_r = int(total_r / count)
                avg_g = int(total_g / count)
                avg_b = int(total_b / count)
                return f"#{avg_r:02x}{avg_g:02x}{avg_b:02x}"
        except Exception:  # noqa: BLE001
            return DEFAULT_OVERLAY_COLOR
        return DEFAULT_OVERLAY_COLOR

    # -------------------------------------------------------------------------
    def _prepare_overlay_response(self, overlay: dict[str, Any]) -> dict[str, Any]:
        response_payload = {
            "name": overlay.get("name"),
            "label": overlay.get("label"),
            "provider": overlay.get("provider"),
            "resolution_m": overlay.get("resolution_m"),
            "mode": overlay.get("mode"),
            "opacity": overlay.get("opacity"),
            "bounds": overlay.get("bounds"),
            "meters_per_pixel": overlay.get("meters_per_pixel"),
            "pixels_per_meter": overlay.get("pixels_per_meter"),
            "detail": overlay.get("detail"),
            "wms_url": overlay.get("wms_url"),
            "attribution": overlay.get("attribution"),
            "mime": overlay.get("mime"),
            "image_base64": overlay.get("image_base64"),
        }
        if overlay.get("mode") == "fill":
            response_payload["fill_color"] = overlay.get("fill_color")
        return response_payload

    # -------------------------------------------------------------------------
    def _build_image_overlay(
        self,
        *,
        entry: LayerProviderEntry,
        payload: dict[str, Any],
        fallback_bounds: list[list[float]],
        index: int,
    ) -> dict[str, Any]:
        image_bytes = payload.pop("image_bytes", b"")
        encoded_image = self.toolkit.encode_image(image_bytes)
        bounds = self._resolve_overlay_bounds(
            payload.get("bbox"),
            source_crs=payload.get("crs"),
            fallback_bounds=fallback_bounds,
        )
        meters_per_pixel = payload.get("meters_per_pixel")
        return {
            "name": entry.name,
            "label": entry.label,
            "provider": entry.provider,
            "resolution_m": entry.resolution_m,
            "mode": "image",
            "opacity": 0.68,
            "bounds": bounds,
            "image_bytes": image_bytes,
            "image_base64": encoded_image,
            "mime": payload.get("mime") or payload.get("format") or "image/png",
            "meters_per_pixel": meters_per_pixel or {},
            "pixels_per_meter": self._compute_pixels_from_meters(meters_per_pixel),
            "wms_url": payload.get("wms_url"),
            "attribution": payload.get("attribution"),
            "detail": None,
            "z_index": 200 + index,
        }

    # -------------------------------------------------------------------------
    def _build_fill_overlay(
        self,
        *,
        entry: LayerProviderEntry,
        bounds: list[list[float]],
        index: int,
        pixels_per_meter: dict[str, float],
        fill_color: str | None,
    ) -> dict[str, Any]:
        color_value = fill_color or DEFAULT_OVERLAY_COLOR
        return {
            "name": entry.name,
            "label": entry.label,
            "provider": entry.provider,
            "resolution_m": entry.resolution_m,
            "mode": "fill",
            "fill_color": color_value,
            "opacity": 0.4,
            "bounds": bounds,
            "image_bytes": b"",
            "image_base64": "",
            "mime": "image/png",
            "meters_per_pixel": {},
            "pixels_per_meter": pixels_per_meter,
            "wms_url": None,
            "attribution": entry.provider,
            "detail": (
                "Layer resolution is lower than the current map extent, "
                "displaying a uniform overlay."
            ),
            "z_index": 200 + index,
        }

    # -------------------------------------------------------------------------
    def _should_render_as_fill(
        self,
        *,
        resolution_m: float | None,
        span_x_m: float,
        span_y_m: float,
        overlay_meters_per_pixel: dict[str, float] | None = None,
        map_meters_per_pixel: dict[str, float] | None = None,
    ) -> bool:
        if overlay_meters_per_pixel and map_meters_per_pixel:
            overlay_min = min(
                float(overlay_meters_per_pixel.get("x", 0.0) or 0.0),
                float(overlay_meters_per_pixel.get("y", 0.0) or 0.0),
            )
            map_max = max(
                float(map_meters_per_pixel.get("x", 0.0) or 0.0),
                float(map_meters_per_pixel.get("y", 0.0) or 0.0),
            )
            if overlay_min > 0 and map_max > 0:
                ratio = overlay_min / map_max
                if ratio <= 8.0:
                    return False
        if resolution_m is None:
            return False
        if span_x_m <= 0 or span_y_m <= 0:
            return True
        min_pixels = min(span_x_m, span_y_m) / resolution_m
        return min_pixels < 1.0

    # -------------------------------------------------------------------------
    def _resolve_overlay_bounds(
        self,
        bbox: list[float] | None,
        *,
        source_crs: str | None,
        fallback_bounds: list[list[float]],
    ) -> list[list[float]]:
        if bbox is None:
            return fallback_bounds
        selected_crs = source_crs or "EPSG:4326"
        target_bbox = self.toolkit.harmonize_bbox_crs(
            bbox,
            source_crs=selected_crs,
            target_crs="EPSG:4326",
        )
        if target_bbox is None:
            return fallback_bounds
        return self._bbox_to_bounds(target_bbox)

    # -------------------------------------------------------------------------
    def _bbox_to_bounds(self, bbox: list[float]) -> list[list[float]]:
        minx, miny, maxx, maxy = bbox
        return [[miny, minx], [maxy, maxx]]


###############################################################################
class MapSearchEndpoint:
    def __init__(
        self,
        router: APIRouter,
        sanitization_service: LocationSanitizationService,
        normatim_service: NormatimService,
        toolkit: MapSearchToolkit,
        rendering_service: MapRenderingService,
        job_manager: JobManager,
        catalog_service: GeospatialCatalogService,
    ) -> None:
        self.router = router
        self.sanitization_service = sanitization_service
        self.normatim_service = normatim_service
        self.toolkit = toolkit
        self.renderer = rendering_service
        self.job_manager = job_manager
        self.catalog_service = catalog_service
        self.serializer = DataSerializer()

    # -------------------------------------------------------------------------
    def resolve_coordinate_pair(
        self,
        payload: LocationSearchRequest | None,
        response_payload: dict[str, Any] | None,
        fallback: dict[str, Any],
    ) -> CoordinatePair | None:
        payload_snapshot = (
            response_payload.get("payload", {}) if response_payload else {}
        )
        if payload:
            coordinates = self.toolkit.extract_coordinate_pair(
                payload, payload_snapshot
            )
            if coordinates:
                return coordinates
            coordinates = self.toolkit.extract_coordinate_pair(
                payload, payload.model_dump()
            )
            if coordinates:
                return coordinates
        lon_candidate = fallback.get("longitude")
        lat_candidate = fallback.get("latitude")
        if lon_candidate is None or lat_candidate is None:
            return None
        try:
            lon_value = float(lon_candidate)
            lat_value = float(lat_candidate)
        except (TypeError, ValueError):
            return None
        return lon_value, lat_value

    # -------------------------------------------------------------------------
    def _coerce_coordinate_scalar(self, value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        return None

    # -------------------------------------------------------------------------
    def format_coordinate_pair(self, coordinates: CoordinatePair | None) -> str | None:
        if coordinates is None:
            return None
        lon, lat = coordinates
        return json.dumps({"longitude": lon, "latitude": lat})

    # -------------------------------------------------------------------------
    def build_search_session_record(
        self,
        *,
        payload: LocationSearchRequest | None,
        response_payload: dict[str, Any] | None,
        fallback: dict[str, Any],
        state: str,
    ) -> dict[str, Any]:
        coordinates = self.resolve_coordinate_pair(payload, response_payload, fallback)
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
        record = {
            "id": None,
            "created_at": datetime.utcnow(),
            "user": fallback.get("user"),
            "country": payload.country if payload else fallback.get("country"),
            "city": payload.city if payload else fallback.get("city"),
            "address": payload.address if payload else fallback.get("address"),
            "coordinates": self.format_coordinate_pair(coordinates),
            "base_map": payload.map_tiles if payload else fallback.get("map_tiles"),
            "geospatial_layers": json.dumps(persisted_selection),
            "state": state,
        }
        return record

    # -------------------------------------------------------------------------
    def _resolve_overlay_ids(self, payload: LocationSearchRequest) -> list[str]:
        legacy_layers = self.toolkit.normalize_layers(payload.filters)
        explicit_overlays = self.toolkit.normalize_layers(payload.overlay_ids)
        resolved = list(explicit_overlays)
        for layer in legacy_layers:
            if layer not in resolved:
                resolved.append(layer)
        return resolved

    # -------------------------------------------------------------------------
    async def build_map_session(
        self,
        *,
        payload: LocationSearchRequest,
        search_payload: dict[str, Any],
        satellite_payload: dict[str, Any],
    ) -> dict[str, Any]:
        overlays = self.catalog_service.resolve_overlays(
            self._resolve_overlay_ids(payload)
        )
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
        latitude = search_payload.get("latitude")
        longitude = search_payload.get("longitude")
        try:
            lat_value = float(latitude) if latitude is not None else None
            lon_value = float(longitude) if longitude is not None else None
        except (TypeError, ValueError):
            lat_value = None
            lon_value = None
        radius_m = float(payload.radius_m or 2500.0)
        insights = await self.catalog_service.fetch_insights(
            latitude=lat_value,
            longitude=lon_value,
            overlay_ids=[item["id"] for item in overlays],
            radius_m=radius_m,
        )
        compliance_warnings = self.catalog_service.resolve_compliance_warnings(
            basemap=basemap,
            overlays=overlays,
        )
        center = {
            "latitude": lat_value,
            "longitude": lon_value,
        }
        bounds = satellite_payload.get("bbox")
        return {
            "center": center,
            "bounds": bounds,
            "basemap": basemap,
            "overlays": overlays,
            "insights": insights,
            "compliance_warnings": compliance_warnings,
        }

    # -------------------------------------------------------------------------
    async def record_search_session(
        self,
        *,
        payload: LocationSearchRequest | None,
        response_payload: dict[str, Any] | None,
        fallback: dict[str, Any],
        state: str,
    ) -> None:
        record = self.build_search_session_record(
            payload=payload,
            response_payload=response_payload,
            fallback=fallback,
            state=state,
        )
        try:
            await asyncio.to_thread(self.serializer.insert_search_session, record)
        except Exception as exc:
            logger.warning("Failed to store search session: %s", exc)

    # -------------------------------------------------------------------------
    async def get_location_coordinates(
        self, payload: LocationSearchRequest
    ) -> dict[str, object]:
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
            normatim_candidate = await self.normatim_service.extract_coordinates(
                address=sanitized_location["address"] or "",
                city=sanitized_location["city"],
                country_name=sanitized_location["country"],
                country_code=sanitized_location["country_code"],
            )
            if normatim_candidate:
                latitude = normatim_candidate.get("lat")
                longitude = normatim_candidate.get("lon")
                if latitude is not None and longitude is not None:
                    try:
                        lat_value = float(latitude)
                        lon_value = float(longitude)
                    except (TypeError, ValueError):
                        lat_value = None
                        lon_value = None
                    if lat_value is not None and lon_value is not None:
                        response_payload["latitude"] = lat_value
                        response_payload["longitude"] = lon_value

                if normatim_candidate.get("bbox"):
                    response_payload["bbox"] = normatim_candidate["bbox"]
                if normatim_candidate.get("confidence") is not None:
                    response_payload["confidence"] = normatim_candidate["confidence"]
        else:
            if payload.latitude is not None and payload.longitude is not None:
                response_payload["latitude"] = payload.latitude
                response_payload["longitude"] = payload.longitude
                bbox = await self.normatim_service.extract_bbox_from_coordinates(
                    latitude=payload.latitude,
                    longitude=payload.longitude,
                )
                if bbox:
                    response_payload["bbox"] = bbox

        return response_payload

    # -------------------------------------------------------------------------
    async def process_location_search(
        self, payload: LocationSearchRequest
    ) -> dict[str, Any]:
        search_payload = await self.get_location_coordinates(payload)
        try:
            satellite_payload = await self.renderer.build_satellite_payload(
                payload, search_payload
            )
        except (GIBSValidationError, MapValidationError, LayerProviderError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        except (GIBSRequestError, MapRequestError) as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc
        search_payload["satellite_imagery"] = satellite_payload
        map_session = await self.build_map_session(
            payload=payload,
            search_payload=search_payload,
            satellite_payload=satellite_payload,
        )
        search_payload["map_session"] = map_session
        search_payload["compliance_warnings"] = map_session.get(
            "compliance_warnings", []
        )

        # Fetch elevation data for the search location
        lat = search_payload.get("latitude")
        lon = search_payload.get("longitude")
        lat_value = self._coerce_coordinate_scalar(lat)
        lon_value = self._coerce_coordinate_scalar(lon)
        if lat_value is not None and lon_value is not None:
            try:
                elevation_data = await elevation_service.get_elevation(
                    lat_value, lon_value
                )
                search_payload["elevation"] = elevation_data
            except Exception as exc:
                logger.warning("Failed to fetch elevation: %s", exc)
                search_payload["elevation"] = None

        return {
            "status_message": MAP_SEARCH_STATUS_MESSAGE,
            "payload": search_payload,
            "map_session": map_session,
            "compliance_warnings": map_session.get("compliance_warnings", []),
        }

    # -------------------------------------------------------------------------
    async def process_location_search_job(
        self,
        *,
        payload: LocationSearchRequest,
        request_context: dict[str, Any],
        job_id: str,
    ) -> dict[str, Any]:
        response_payload: dict[str, Any] | None = None
        try:
            self.job_manager.update_progress(job_id, MAP_SEARCH_JOB_PROGRESS_COORDINATES)
            search_payload = await self.get_location_coordinates(payload)
            if self.job_manager.should_stop(job_id):
                await self.record_search_session(
                    payload=payload,
                    response_payload=response_payload,
                    fallback=request_context,
                    state=JOB_STATUS_CANCELLED,
                )
                return {}
            self.job_manager.update_progress(job_id, MAP_SEARCH_JOB_PROGRESS_IMAGERY)

            try:
                satellite_payload = await self.renderer.build_satellite_payload(
                    payload, search_payload
                )
            except (GIBSValidationError, MapValidationError, LayerProviderError) as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(exc),
                ) from exc
            except (GIBSRequestError, MapRequestError) as exc:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=str(exc),
                ) from exc

            search_payload["satellite_imagery"] = satellite_payload
            map_session = await self.build_map_session(
                payload=payload,
                search_payload=search_payload,
                satellite_payload=satellite_payload,
            )
            search_payload["map_session"] = map_session
            search_payload["compliance_warnings"] = map_session.get(
                "compliance_warnings", []
            )
            self.job_manager.update_progress(job_id, MAP_SEARCH_JOB_PROGRESS_POSTPROCESS)

            lat = search_payload.get("latitude")
            lon = search_payload.get("longitude")
            lat_value = self._coerce_coordinate_scalar(lat)
            lon_value = self._coerce_coordinate_scalar(lon)
            if lat_value is not None and lon_value is not None:
                try:
                    elevation_data = await elevation_service.get_elevation(
                        lat_value, lon_value
                    )
                    search_payload["elevation"] = elevation_data
                except Exception as exc:
                    logger.warning("Failed to fetch elevation: %s", exc)
                    search_payload["elevation"] = None

            response_payload = build_search_response(
                search_payload=search_payload,
                map_session=map_session,
            )
            self.job_manager.update_result(job_id, response_payload)
            if self.job_manager.should_stop(job_id):
                await self.record_search_session(
                    payload=payload,
                    response_payload=response_payload,
                    fallback=request_context,
                    state=JOB_STATUS_CANCELLED,
                )
                return response_payload
            await self.record_search_session(
                payload=payload,
                response_payload=response_payload,
                fallback=request_context,
                state="success",
            )
            self.job_manager.update_progress(job_id, MAP_SEARCH_JOB_PROGRESS_PERSISTED)
            return response_payload
        except HTTPException as exc:
            await self.record_search_session(
                payload=payload,
                response_payload=response_payload,
                fallback=request_context,
                state="failed",
            )
            error_detail = exc.detail
            message = str(error_detail) if error_detail is not None else str(exc)
            raise RuntimeError(message) from exc
        except Exception:
            await self.record_search_session(
                payload=payload,
                response_payload=response_payload,
                fallback=request_context,
                state="failed",
            )
            raise

    # -------------------------------------------------------------------------
    async def search_by_location(
        self,
        datetime_value: datetime | str | None = Body(default=None, alias="datetime"),
        time_of_day: time | str | None = Body(default=None),
        timeline_year: int | None = Body(default=None),
        country: str | None = Body(default=None),
        city: str | None = Body(default=None),
        address: str | None = Body(default=None),
        use_coordinates: bool = Body(default=False),
        latitude: float | None = Body(default=None),
        longitude: float | None = Body(default=None),
        geospatial_layers: list[str] = Body(default_factory=list),
        basemap_id: str | None = Body(default=None),
        overlay_ids: list[str] = Body(default_factory=list),
        aoi: dict[str, Any] | None = Body(default=None),
        commute: dict[str, Any] | None = Body(default=None),
        bbox: list[float] | None = Body(default=None),
        radius_m: float | None = Body(default=None),
        map_size_m: float | None = Body(default=None),
        map_tiles: str | None = Body(default=None),
        image_width: int | None = Body(default=None),
        image_height: int | None = Body(default=None),
        image_crs: str | None = Body(default=None),
        image_format: str | None = Body(default=None),
    ) -> SearchByLocationResponse:
        payload: LocationSearchRequest | None = None
        response_payload: dict[str, Any] | None = None
        request_context = build_request_context(
            country=country,
            city=city,
            address=address,
            longitude=longitude,
            latitude=latitude,
            geospatial_layers=geospatial_layers,
            overlay_ids=overlay_ids,
            basemap_id=basemap_id,
            map_tiles=map_tiles,
        )
        try:
            payload_data = build_location_search_payload_data(
                datetime_value=datetime_value,
                time_of_day=time_of_day,
                timeline_year=timeline_year,
                country=country,
                city=city,
                address=address,
                use_coordinates=use_coordinates,
                latitude=latitude,
                longitude=longitude,
                geospatial_layers=geospatial_layers,
                basemap_id=basemap_id,
                overlay_ids=overlay_ids,
                aoi=aoi,
                commute=commute,
                bbox=bbox,
                radius_m=radius_m,
                map_size_m=map_size_m,
                map_tiles=request_context["map_tiles"],
                image_crs=image_crs,
                image_format=image_format,
            )
            payload = await asyncio.to_thread(
                LocationSearchRequest.model_validate, payload_data
            )
            response_payload = await self.process_location_search(payload)
            typed_response = await asyncio.to_thread(
                SearchByLocationResponse.model_validate, response_payload
            )
            await self.record_search_session(
                payload=payload,
                response_payload=response_payload,
                fallback=request_context,
                state="success",
            )
            return typed_response
        except ValidationError as exc:
            await self.record_search_session(
                payload=payload,
                response_payload=response_payload,
                fallback=request_context,
                state="failed",
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=sanitize_validation_errors(exc.errors()),
            ) from exc
        except Exception:
            await self.record_search_session(
                payload=payload,
                response_payload=response_payload,
                fallback=request_context,
                state="failed",
            )
            raise

    # -------------------------------------------------------------------------
    async def start_search_job(
        self,
        datetime_value: datetime | str | None = Body(default=None, alias="datetime"),
        time_of_day: time | str | None = Body(default=None),
        timeline_year: int | None = Body(default=None),
        country: str | None = Body(default=None),
        city: str | None = Body(default=None),
        address: str | None = Body(default=None),
        use_coordinates: bool = Body(default=False),
        latitude: float | None = Body(default=None),
        longitude: float | None = Body(default=None),
        geospatial_layers: list[str] = Body(default_factory=list),
        basemap_id: str | None = Body(default=None),
        overlay_ids: list[str] = Body(default_factory=list),
        aoi: dict[str, Any] | None = Body(default=None),
        commute: dict[str, Any] | None = Body(default=None),
        bbox: list[float] | None = Body(default=None),
        radius_m: float | None = Body(default=None),
        map_size_m: float | None = Body(default=None),
        map_tiles: str | None = Body(default=None),
        image_width: int | None = Body(default=None),
        image_height: int | None = Body(default=None),
        image_crs: str | None = Body(default=None),
        image_format: str | None = Body(default=None),
    ) -> JobStartResponse:
        payload: LocationSearchRequest | None = None
        response_payload: dict[str, Any] | None = None
        request_context = build_request_context(
            country=country,
            city=city,
            address=address,
            longitude=longitude,
            latitude=latitude,
            geospatial_layers=geospatial_layers,
            overlay_ids=overlay_ids,
            basemap_id=basemap_id,
            map_tiles=map_tiles,
        )
        try:
            payload_data = build_location_search_payload_data(
                datetime_value=datetime_value,
                time_of_day=time_of_day,
                timeline_year=timeline_year,
                country=country,
                city=city,
                address=address,
                use_coordinates=use_coordinates,
                latitude=latitude,
                longitude=longitude,
                geospatial_layers=geospatial_layers,
                basemap_id=basemap_id,
                overlay_ids=overlay_ids,
                aoi=aoi,
                commute=commute,
                bbox=bbox,
                radius_m=radius_m,
                map_size_m=map_size_m,
                map_tiles=request_context["map_tiles"],
                image_crs=image_crs,
                image_format=image_format,
            )

            payload = await asyncio.to_thread(
                LocationSearchRequest.model_validate, payload_data
            )
        except ValidationError as exc:
            await self.record_search_session(
                payload=payload,
                response_payload=response_payload,
                fallback=request_context,
                state="failed",
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=sanitize_validation_errors(exc.errors()),
            ) from exc

        job_id = self.job_manager.start_job(
            job_type="map_search",
            runner=run_map_search_job,
            kwargs={
                "endpoint": self,
                "payload": payload,
                "request_context": request_context,
            },
        )
        job_status = self.job_manager.get_job_status(job_id)
        if job_status is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=MAP_SEARCH_JOB_INIT_ERROR,
            )
        return JobStartResponse(
            job_id=job_id,
            job_type=job_status["job_type"],
            status=job_status["status"],
            message=MAP_SEARCH_JOB_START_MESSAGE,
            poll_interval=server_settings.jobs.polling_interval,
        )

    # -------------------------------------------------------------------------
    async def get_search_job_status(self, job_id: str) -> JobStatusResponse:
        job_status = self.job_manager.get_job_status(job_id)
        if job_status is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job not found: {job_id}",
            )
        return JobStatusResponse(**job_status)

    # -------------------------------------------------------------------------
    async def cancel_search_job(self, job_id: str) -> JobCancelResponse:
        job_status = self.job_manager.get_job_status(job_id)
        if job_status is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job not found: {job_id}",
            )
        success = self.job_manager.cancel_job(job_id)
        return JobCancelResponse(
            job_id=job_id,
            success=success,
            message=(
                MAP_SEARCH_CANCELLATION_REQUESTED
                if success
                else MAP_SEARCH_CANCELLATION_NOT_ALLOWED
            ),
        )

    # -------------------------------------------------------------------------
    async def get_catalog(self) -> GeospatialCatalogResponse:
        catalog = await asyncio.to_thread(self.catalog_service.list_catalog)
        return GeospatialCatalogResponse.model_validate(catalog)

    # -------------------------------------------------------------------------
    def add_routes(self) -> None:
        self.router.add_api_route(
            MAPS_CATALOG_ROUTE,
            self.get_catalog,
            methods=["GET"],
            response_model=GeospatialCatalogResponse,
            status_code=status.HTTP_200_OK,
        )
        self.router.add_api_route(
            MAPS_SEARCH_ROUTE,
            self.search_by_location,
            methods=["POST"],
            response_model=SearchByLocationResponse,
            status_code=status.HTTP_200_OK,
        )
        self.router.add_api_route(
            MAPS_JOBS_ROUTE,
            self.start_search_job,
            methods=["POST"],
            response_model=JobStartResponse,
            status_code=status.HTTP_202_ACCEPTED,
        )
        self.router.add_api_route(
            MAPS_JOB_ROUTE,
            self.get_search_job_status,
            methods=["GET"],
            response_model=JobStatusResponse,
            status_code=status.HTTP_200_OK,
        )
        self.router.add_api_route(
            MAPS_JOB_ROUTE,
            self.cancel_search_job,
            methods=["DELETE"],
            response_model=JobCancelResponse,
            status_code=status.HTTP_200_OK,
        )


toolkit = MapSearchToolkit(
    gibs_service=gibs_service,
    default_layer=server_settings.gibs.default_layer,
)
rendering_service = MapRenderingService(
    toolkit=toolkit,
    map_service=map_service,
    gibs_service=gibs_service,
    layer_service=layer_service,
)
search_endpoint = MapSearchEndpoint(
    router=router,
    sanitization_service=sanitization_service,
    normatim_service=normatim_service,
    toolkit=toolkit,
    rendering_service=rendering_service,
    job_manager=job_manager,
    catalog_service=catalog_service,
)
search_endpoint.add_routes()
