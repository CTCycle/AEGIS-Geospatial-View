from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any

from server.configurations import get_server_settings
from server.domain.gibs import Capabilities
from server.repositories.catalog.reference_repository import ReferenceCatalogRepository
from server.repositories.database import get_database
from server.repositories.database.contracts import DatabaseBackend
from server.services.geospatial.gibs_errors import GIBSRequestError
from server.services.geospatial.gibs_runtime import GIBSRuntimeMixin

type BBox = list[float]
type LayerStore = dict[str, object]


###############################################################################
class CapabilitiesCache:
    def __init__(self, ttl_s: float) -> None:
        self.ttl_s = ttl_s
        self.store: dict[str, Capabilities] = {}
        self.lock = threading.Lock()

    # -------------------------------------------------------------------------
    def get(self, key: str) -> Capabilities | None:
        with self.lock:
            entry = self.store.get(key)
            if not entry:
                return None
            if time.time() - entry.retrieved_at > self.ttl_s:
                self.store.pop(key, None)
                return None
            return entry

    # -------------------------------------------------------------------------
    def set(self, key: str, value: Capabilities) -> None:
        with self.lock:
            self.store[key] = value


###############################################################################
class ResponseCache:
    def __init__(self, max_entries: int) -> None:
        self.max_entries = max_entries
        self.cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self.lock = threading.Lock()

    # -------------------------------------------------------------------------
    def get(self, key: str) -> dict[str, Any] | None:
        with self.lock:
            value = self.cache.get(key)
            if value is None:
                return None
            self.cache.move_to_end(key)
            return value

    # -------------------------------------------------------------------------
    def set(self, key: str, value: dict[str, Any]) -> None:
        with self.lock:
            self.cache[key] = value
            self.cache.move_to_end(key)
            while len(self.cache) > self.max_entries:
                self.cache.popitem(last=False)


###############################################################################
class GIBSService(GIBSRuntimeMixin):
    def __init__(
        self,
        *,
        user_agent: str | None = None,
        timeout_s: float | None = None,
        capabilities_ttl_s: float | None = None,
        cache_entries: int | None = None,
        retry_backoff_s: float | None = None,
        bbox_precision: int | None = None,
        min_visual_radius_m: float | None = None,
        database: DatabaseBackend | None = None,
        reference_repository: ReferenceCatalogRepository | None = None,
    ) -> None:
        settings = get_server_settings().gibs
        self.user_agent = user_agent or settings.user_agent
        self.timeout_s = timeout_s if timeout_s is not None else settings.timeout
        ttl_value = (
            capabilities_ttl_s
            if capabilities_ttl_s is not None
            else settings.capabilities_ttl_s
        )
        self.capabilities_cache = CapabilitiesCache(ttl_value)
        cache_size = (
            cache_entries if cache_entries is not None else settings.max_cache_entries
        )
        self.response_cache = ResponseCache(cache_size)
        self.retry_backoff_s = (
            retry_backoff_s if retry_backoff_s is not None else settings.retry_backoff_s
        )
        self.bbox_precision = (
            bbox_precision if bbox_precision is not None else settings.bbox_precision
        )
        self.min_visual_radius_m = (
            min_visual_radius_m
            if min_visual_radius_m is not None
            else settings.min_visual_radius_m
        )
        resolved_database = database or get_database().backend
        self.database = resolved_database
        self.reference_repository = reference_repository or ReferenceCatalogRepository(
            resolved_database
        )
        self.layer_native_resolution_m = (
            self.reference_repository.load_gibs_layer_native_resolution_map()
        )
        self.layer_date_fallback_days = (
            self.reference_repository.load_gibs_layer_date_fallback_days_map()
        )
        self.wms_base_endpoints = dict(settings.wms_base_endpoints)
        self.nasa_attribution = settings.nasa_attribution

    # -------------------------------------------------------------------------
    def resolve_layer_meters_per_pixel(self, layer: str) -> tuple[float, ...]:
        fallback = self.layer_native_resolution_m.get(layer)
        return (fallback,) if fallback else tuple()

    # -------------------------------------------------------------------------
    def fetch_image(
        self,
        *,
        lon: float | None,
        lat: float | None,
        bbox: BBox | tuple[float, float, float, float] | None,
        radius_m: float | None,
        date: str,
        layer: str,
        width: int | None = None,
        height: int | None = None,
        crs: str = "EPSG:3857",
        format: str = "image/png",
        style: str | None = None,
        wms_version: str = "1.3.0",
        timeout_s: int | None = None,
        skip_bbox_expansion: bool = False,
    ) -> dict[str, Any]:
        request_crs = crs.upper()
        bbox_provided = bbox is not None
        effective_radius = (
            None if bbox_provided else self.resolve_effective_radius(radius_m)
        )
        style_value = self.normalize_style(style)
        normalized_bbox = self.normalize_bbox(
            bbox=bbox,
            lon=lon,
            lat=lat,
            radius_m=effective_radius,
            target_crs=request_crs,
        )
        settings = get_server_settings().gibs
        resolved_width = width if width is not None else settings.image_width
        resolved_height = height if height is not None else settings.image_height
        self.validate_dimensions(resolved_width, resolved_height)
        format_lower = format.lower()
        capabilities, _ = self.resolve_capabilities_for_layer(
            requested_crs=request_crs,
            layer=layer,
            wms_version=wms_version,
        )
        layer_meta = self.extract_layer(layer, capabilities)
        actual_crs = self.resolve_layer_crs(layer_meta, request_crs)
        bbox_for_request = (
            normalized_bbox
            if actual_crs == request_crs
            else self.reproject_bbox(normalized_bbox, actual_crs)
        )
        # When skip_bbox_expansion is True, preserve the exact bbox for overlays
        # to ensure the imagery aligns with the map bounds. Otherwise, expand
        # the bbox to meet minimum resolution requirements for standalone usage.
        if not skip_bbox_expansion:
            bbox_for_request = self.ensure_bbox_resolution(
                layer,
                bbox_for_request,
                actual_crs,
                resolved_width,
                resolved_height,
            )
        meters_per_pixel = self.compute_meters_per_pixel(
            bbox_for_request, actual_crs, resolved_width, resolved_height
        )
        self.validate_format(format_lower, layer_meta, capabilities)
        imagery_date_value = self.parse_imagery_date(date)
        supported_imagery_date = self.resolve_supported_imagery_date(
            imagery_date_value, layer_meta
        )
        timeout = timeout_s or self.timeout_s
        last_error: GIBSRequestError | None = None
        for imagery_date_value in self.resolve_request_dates(
            layer=layer,
            imagery_date=supported_imagery_date,
        ):
            imagery_date_token = imagery_date_value.isoformat()
            cache_key = self.build_cache_key(
                layer=layer,
                imagery_date=imagery_date_token,
                bbox=bbox_for_request,
                crs=actual_crs,
                width=resolved_width,
                height=resolved_height,
                format_value=format_lower,
                style_value=style_value,
            )
            cached = self.response_cache.get(cache_key)
            if cached:
                return dict(cached)
            query = self.build_query(
                base_url=self.resolve_base_url(actual_crs),
                bbox=bbox_for_request,
                crs=actual_crs,
                width=resolved_width,
                height=resolved_height,
                layer=layer,
                imagery_date=imagery_date_token,
                format_value=format_lower,
                style_value=style_value,
                wms_version=wms_version,
            )
            try:
                image_bytes, mime, final_url = self.execute_request(query, timeout)
            except GIBSRequestError as exc:
                last_error = exc
                if self.should_retry_previous_date(layer=layer, error=exc):
                    continue
                raise
            response = {
                "image_bytes": image_bytes,
                "mime": mime,
                "bbox": bbox_for_request,
                "crs": actual_crs,
                "date": imagery_date_token,
                "layer": layer,
                "width": resolved_width,
                "height": resolved_height,
                "wms_url": final_url,
                "attribution": self.nasa_attribution,
                "meters_per_pixel": meters_per_pixel,
            }
            self.response_cache.set(cache_key, dict(response))
            return response
        if last_error is not None:
            raise last_error
        raise GIBSRequestError("GIBS GetMap failed without a usable fallback date.")
