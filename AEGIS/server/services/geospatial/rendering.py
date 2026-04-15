from __future__ import annotations

import asyncio
import base64
from io import BytesIO
from typing import Any

from PIL import Image

from AEGIS.server.configurations import get_server_settings
from AEGIS.server.domain.geographics import LocationSearchRequest
from AEGIS.server.services.geospatial.gibs import GIBSService, GIBSValidationError
from AEGIS.server.services.geospatial.layers import (
    LayerProviderEntry,
    LayerProviderError,
    LayerProviderService,
)
from AEGIS.server.services.geospatial.maps import MapService, MapValidationError

type CoordinatePair = tuple[float, float]
DEFAULT_OVERLAY_COLOR = "#2563eb"


class MapSearchToolkit:
    def __init__(self, gibs_service: GIBSService, *, default_layer: str) -> None:
        self.gibs_service = gibs_service
        self.default_layer = default_layer

    def select_primary_layer(self, layers: list[str]) -> str | None:
        if not isinstance(layers, list):
            return None
        for value in layers:
            normalized = str(value).strip()
            if normalized and normalized.lower() != "none":
                return normalized
        return None

    def normalize_layer_value(self, value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized or normalized.lower() == "none":
            return None
        return normalized

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

    def resolve_imagery_date(self, payload: LocationSearchRequest) -> str:
        if payload.datetime:
            return payload.datetime.date().isoformat()
        raise GIBSValidationError("Provide datetime to determine imagery date.")

    def resolve_imagery_layer(self, payload: LocationSearchRequest) -> str:
        selected_layer = self.select_primary_layer(payload.filters)
        return selected_layer or self.default_layer

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

    def encode_image(self, data: bytes) -> str:
        if not data:
            return ""
        return base64.b64encode(data).decode("ascii")


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
        map_size_value = payload.map_size_m or get_server_settings().map.default_size_m
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

    def _expand_map_bbox_for_layers(
        self,
        *,
        map_bbox: list[float],
        overlay_layers: list[str],
        payload: LocationSearchRequest,
    ) -> list[float]:
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
        if not overlay_layers:
            return []
        if map_bbox is None or imagery_bbox is None:
            raise GIBSValidationError(
                "Provide bbox to render geospatial overlay layers."
            )
        overlays: list[dict[str, Any]] = []
        imagery_date = self.toolkit.resolve_imagery_date(payload)
        map_bounds = self._bbox_to_bounds(map_bbox)
        for index, layer_name in enumerate(overlay_layers):
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

    def _derive_map_bbox(
        self,
        *,
        bbox_candidate: list[float] | None,
        bbox_source_crs: str | None,
        coordinates: CoordinatePair | None,
        payload: LocationSearchRequest,
    ) -> list[float] | None:
        if payload.bbox:
            explicit = self.toolkit.harmonize_bbox_crs(
                payload.bbox,
                source_crs=payload.image_crs,
                target_crs="EPSG:4326",
            )
            if explicit:
                return explicit
        if isinstance(payload.aoi, dict):
            aoi_bbox = payload.aoi.get("bbox")
            if isinstance(aoi_bbox, list) and len(aoi_bbox) == 4:
                harmonized_aoi = self.toolkit.harmonize_bbox_crs(
                    aoi_bbox,
                    source_crs=payload.image_crs,
                    target_crs="EPSG:4326",
                )
                if harmonized_aoi:
                    return harmonized_aoi
        harmonized = self.toolkit.harmonize_bbox_crs(
            bbox_candidate,
            source_crs=bbox_source_crs,
            target_crs="EPSG:4326",
        )
        if harmonized:
            return harmonized
        if coordinates is not None:
            lon, lat = coordinates
            map_size_value = payload.map_size_m or get_server_settings().map.default_size_m
            return self.map_service.compute_bbox_from_center(lon, lat, map_size_value)
        return None

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
        except Exception:
            return DEFAULT_OVERLAY_COLOR
        return DEFAULT_OVERLAY_COLOR

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

    def _bbox_to_bounds(self, bbox: list[float]) -> list[list[float]]:
        minx, miny, maxx, maxy = bbox
        return [[miny, minx], [maxy, maxx]]
