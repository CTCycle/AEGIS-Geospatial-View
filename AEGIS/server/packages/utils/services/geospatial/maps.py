from __future__ import annotations

import base64
import math
import time
from typing import Any

import folium

from AEGIS.server.packages.configurations import server_settings
from AEGIS.server.packages.constants import (
    COMMON_FOLIUM_MAPS,
    EARTH_RADIUS_M,
    MAX_GEO_LAT,
    MAX_LONGITUDE,
    MIN_GEO_LAT,
    MIN_LONGITUDE,
)

type BBox = list[float]

__all__ = [
    "get_map_tile_options",
    "COMMON_FOLIUM_MAPS",
    "MapServiceError",
    "MapValidationError",
    "MapRequestError",
    "MapService",
]


# -----------------------------------------------------------------------------
def get_map_tile_options(default_tiles: str | None = None) -> dict[str, str]:
    default_value = (default_tiles or "").strip()
    options = {
        name: label for name, label in COMMON_FOLIUM_MAPS.items() if name.strip()
    }
    if default_value and default_value not in options:
        options = {default_value: default_value, **options}
    return options


###############################################################################
class MapServiceError(Exception):
    pass


###############################################################################
class MapValidationError(MapServiceError):
    pass


###############################################################################
class MapRequestError(MapServiceError):
    pass


###############################################################################
class MapService:
    def __init__(
        self,
        *,
        tiles: str | None = None,
        attribution: str | None = None,
        default_delay_s: float | None = None,
    ) -> None:
        config_tiles = (server_settings.map.tiles or "").strip()
        self.tiles = (tiles or config_tiles or "OpenStreetMap").strip()
        self.attribution = (
            attribution or "(c) OpenStreetMap contributors, rendered by Folium"
        )
        if default_delay_s is None:
            default_delay_s = server_settings.map.render_delay_s
        self.default_delay_s = max(float(default_delay_s), 0.0)

    # -------------------------------------------------------------------------
    def normalize_bbox(self, bbox: BBox) -> BBox:
        if len(bbox) != 4:
            raise MapValidationError("BBox must include four values [minx,miny,maxx,maxy].")
        try:
            minx, miny, maxx, maxy = [float(value) for value in bbox]
        except (TypeError, ValueError) as exc:
            raise MapValidationError("BBox values must be numeric.") from exc
        if minx >= maxx or miny >= maxy:
            raise MapValidationError("BBox min values must be smaller than max values.")
        if minx < MIN_LONGITUDE or maxx > MAX_LONGITUDE:
            raise MapValidationError("Longitude values must be within [-180, 180].")
        if miny < MIN_GEO_LAT or maxy > MAX_GEO_LAT:
            raise MapValidationError("Latitude values must be within [-90, 90].")
        return [minx, miny, maxx, maxy]

    # -------------------------------------------------------------------------
    def compute_bbox_from_center(
        self, lon: float, lat: float, size_m: float
    ) -> BBox:
        if size_m <= 0:
            raise MapValidationError("map_size_m must be greater than zero.")
        lat_radians = math.radians(lat)
        half_size = size_m / 2.0
        angular_distance = half_size / EARTH_RADIUS_M
        delta_lat = math.degrees(angular_distance)
        cos_lat = math.cos(lat_radians)
        safe_cos_lat = cos_lat if abs(cos_lat) > 1e-6 else 1e-6
        delta_lon = math.degrees(angular_distance / safe_cos_lat)
        min_lon = max(MIN_LONGITUDE, lon - delta_lon)
        max_lon = min(MAX_LONGITUDE, lon + delta_lon)
        min_lat = max(MIN_GEO_LAT, lat - delta_lat)
        max_lat = min(MAX_GEO_LAT, lat + delta_lat)
        if min_lon >= max_lon or min_lat >= max_lat:
            raise MapValidationError("Computed bbox is invalid for the requested size.")
        return [min_lon, min_lat, max_lon, max_lat]

    # -------------------------------------------------------------------------
    def estimate_bbox_span_m(self, bbox: BBox) -> float:
        minx, miny, maxx, maxy = bbox
        mean_lat = (miny + maxy) / 2.0
        lat_span_rad = math.radians(maxy - miny)
        lon_span_rad = math.radians(maxx - minx)
        lat_span_m = abs(lat_span_rad) * EARTH_RADIUS_M
        lon_span_m = abs(lon_span_rad) * EARTH_RADIUS_M * max(
            math.cos(math.radians(mean_lat)), 1e-6
        )
        return max(lat_span_m, lon_span_m)

    # -------------------------------------------------------------------------
    def resolve_center(
        self, lon: float | None, lat: float | None, bbox: BBox
    ) -> tuple[float, float]:
        if lon is not None and lat is not None:
            return float(lon), float(lat)
        minx, miny, maxx, maxy = bbox
        return (minx + maxx) / 2.0, (miny + maxy) / 2.0

    # -------------------------------------------------------------------------
    def fetch_map_image(
        self,
        *,
        lon: float | None,
        lat: float | None,
        bbox: BBox | None,
        map_size_m: float | None,
        width: int | None = None,
        height: int | None = None,
        tiles: str | None = None,
        overlays: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        map_size_value = map_size_m or server_settings.map.default_size_m
        if bbox is not None:
            map_bbox = self.normalize_bbox(bbox)
            map_size_value = map_size_m or self.estimate_bbox_span_m(map_bbox)
        else:
            if lon is None or lat is None:
                raise MapValidationError("Provide coordinates or bbox for map imagery.")
            map_bbox = self.compute_bbox_from_center(
                float(lon),
                float(lat),
                map_size_value,
            )
        center_lon, center_lat = self.resolve_center(lon, lat, map_bbox)
        try:
            width_value = (
                int(width)
                if width is not None
                else int(server_settings.gibs.image_width)
            )
            height_value = (
                int(height)
                if height is not None
                else int(server_settings.gibs.image_height)
            )
        except (TypeError, ValueError) as exc:
            raise MapValidationError("Image dimensions must be integers.") from exc
        if width_value <= 0 or height_value <= 0:
            raise MapValidationError("Image dimensions must be positive integers.")
        map_object = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=17,
            tiles=None,
            width=width_value,
            height=height_value,
            control_scale=True,
            zoom_control=True,
        )
        base_tiles = tiles or self.tiles
        folium.TileLayer(
            base_tiles,
            name="Base Map",
            attr=self.attribution,
            control=True,
        ).add_to(map_object)
        overlay_entries = overlays or []
        for index, overlay in enumerate(overlay_entries):
            self._add_overlay_layer(map_object, overlay, index)
        folium.LayerControl(position="topright", collapsed=False).add_to(map_object)
        map_object.fit_bounds(
            [[map_bbox[1], map_bbox[0]], [map_bbox[3], map_bbox[2]]]
        )
        start_ts = time.perf_counter()
        try:
            image_bytes = map_object._to_png(self.default_delay_s)  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            raise MapRequestError("Unable to render map image.") from exc
        render_time_s = round(time.perf_counter() - start_ts, 3)
        map_html = map_object.get_root().render()
        return {
            "image_bytes": image_bytes,
            "mime": "image/png",
            "bbox": map_bbox,
            "crs": "EPSG:4326",
            "width": width_value,
            "height": height_value,
            "tiles": base_tiles,
            "attribution": self.attribution,
            "map_size_m": map_size_value,
            "center": {"longitude": center_lon, "latitude": center_lat},
            "render_time_s": render_time_s,
            "map_html": map_html,
        }

    # -------------------------------------------------------------------------
    def _add_overlay_layer(
        self, map_object: folium.Map, overlay: dict[str, Any], index: int
    ) -> None:
        bounds = self._normalize_bounds(overlay.get("bounds"))
        if bounds is None:
            return
        layer_name = (
            str(overlay.get("label") or overlay.get("name") or f"Layer {index + 1}")
        )
        opacity = float(overlay.get("opacity", 0.65))
        mode = str(overlay.get("mode") or "image").lower()
        overlay_group = folium.FeatureGroup(name=layer_name, show=True)
        if mode == "fill":
            fill_color = str(overlay.get("fill_color") or "#2563eb")
            folium.Rectangle(
                bounds=bounds,
                color=fill_color,
                fill=True,
                fill_color=fill_color,
                fill_opacity=opacity,
                weight=0,
            ).add_to(overlay_group)
        else:
            source = self._resolve_overlay_source(overlay)
            if source is None:
                return
            folium.raster_layers.ImageOverlay(
                image=source,
                bounds=bounds,
                opacity=opacity,
                name=layer_name,
                interactive=False,
                zindex=int(overlay.get("z_index", 200 + index)),
            ).add_to(overlay_group)
        overlay_group.add_to(map_object)

    # -------------------------------------------------------------------------
    def _resolve_overlay_source(self, overlay: dict[str, Any]) -> str | None:
        source = overlay.get("image_url")
        if isinstance(source, str):
            stripped = source.strip()
            if stripped:
                return stripped
        image_bytes = overlay.get("image_bytes")
        if not image_bytes:
            return None
        mime = str(overlay.get("mime") or "image/png").strip()
        encoded = base64.b64encode(image_bytes).decode("ascii")
        return f"data:{mime};base64,{encoded}"

    # -------------------------------------------------------------------------
    def _normalize_bounds(self, bounds: Any) -> list[list[float]] | None:
        if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
            return None
        normalized: list[list[float]] = []
        for coordinate in bounds:
            if not isinstance(coordinate, (list, tuple)) or len(coordinate) != 2:
                return None
            try:
                lat = float(coordinate[0])
                lon = float(coordinate[1])
            except (TypeError, ValueError):
                return None
            normalized.append([lat, lon])
        return normalized
