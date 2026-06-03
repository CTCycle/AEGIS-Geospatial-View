from __future__ import annotations

import math
import time
from datetime import date, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from server.domain.gibs import Capabilities, LayerMetadata
from server.common.constants import (
    CAPABILITIES_QUERY,
    EARTH_RADIUS_M,
    GIBS_MAX_IMAGE_DIMENSION,
    GIBS_MIN_IMAGE_DIMENSION,
    MAX_GEO_LAT,
    MAX_LONGITUDE,
    MAX_MERCATOR_LAT,
    MAX_WEB_MERCATOR,
    MIN_GEO_LAT,
    MIN_LONGITUDE,
    MIN_MERCATOR_LAT,
    ORIGIN_SHIFT,
)
from server.common.logger import logger
from server.services.geospatial.gibs_errors import (
    GIBSPayloadIntegrityError,
    GIBSRequestError,
    GIBSValidationError,
)

type BBox = list[float]


type LayerStore = dict[str, LayerMetadata]


def clamp(value: float, lower: float, upper: float) -> float:
    return max(min(value, upper), lower)


class GIBSRuntimeMixin:
    def normalize_bbox(
        self,
        *,
        bbox: BBox | tuple[float, float, float, float] | None,
        lon: float | None,
        lat: float | None,
        radius_m: float | None,
        target_crs: str,
    ) -> BBox:
        if bbox is not None:
            if len(bbox) != 4:
                raise GIBSValidationError(
                    "BBox must include four values [minx, miny, maxx, maxy]."
                )
            try:
                normalized = [float(value) for value in bbox]
            except (TypeError, ValueError) as exc:
                raise GIBSValidationError("BBox values must be numeric.") from exc
            self.validate_bbox_values(normalized, target_crs)
            return normalized
        if lon is None or lat is None:
            raise GIBSValidationError(
                "Coordinates are required when bbox is not provided."
            )
        radius = radius_m if radius_m is not None else 2500.0
        if radius <= 0:
            raise GIBSValidationError("radius_m must be greater than zero.")
        if target_crs == "EPSG:3857":
            center_x, center_y = self.lonlat_to_mercator(lon, lat)
            bbox_mercator = [
                center_x - radius,
                center_y - radius,
                center_x + radius,
                center_y + radius,
            ]
            self.validate_bbox_values(bbox_mercator, target_crs)
            return bbox_mercator
        if target_crs == "EPSG:4326":
            bbox_geographic = self.compute_geographic_bbox(lon, lat, radius)
            self.validate_bbox_values(bbox_geographic, target_crs)
            return bbox_geographic
        raise GIBSValidationError(f"Unsupported target CRS '{target_crs}'.")

    # -------------------------------------------------------------------------
    def validate_bbox_values(self, bbox: BBox, crs: str) -> None:
        if len(bbox) != 4:
            raise GIBSValidationError(
                "BBox must include four values [minx, miny, maxx, maxy]."
            )
        for value in bbox:
            if not math.isfinite(value):
                raise GIBSValidationError("BBox values must be finite numbers.")
        minx, miny, maxx, maxy = bbox
        if minx >= maxx or miny >= maxy:
            raise GIBSValidationError(
                "BBox min values must be smaller than max values."
            )
        if crs == "EPSG:3857":
            for value in bbox:
                if abs(value) > MAX_WEB_MERCATOR:
                    raise GIBSValidationError(
                        "BBox exceeds EPSG:3857 extent +/-20037508.3427892."
                    )
        elif crs == "EPSG:4326":
            if minx < MIN_LONGITUDE or maxx > MAX_LONGITUDE:
                raise GIBSValidationError("Longitude must be within [-180, 180].")
            if miny < MIN_GEO_LAT or maxy > MAX_GEO_LAT:
                raise GIBSValidationError("Latitude must be within [-90, 90].")

    # -------------------------------------------------------------------------
    def normalize_date(self, value: str) -> str:
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise GIBSValidationError(
                f"Date '{value}' must follow YYYY-MM-DD format."
            ) from exc
        return parsed.isoformat()

    # -------------------------------------------------------------------------
    def build_cache_key(
        self,
        *,
        layer: str,
        imagery_date: str,
        bbox: BBox,
        crs: str,
        width: int,
        height: int,
        format_value: str,
        style_value: str,
    ) -> str:
        bbox_token = ",".join(f"{value:.4f}" for value in bbox)
        return (
            f"{layer}|{imagery_date}|{crs}|{width}x{height}"
            f"|{format_value}|{style_value}|{bbox_token}"
        )

    # -------------------------------------------------------------------------
    def load_capabilities(self, crs: str, version: str) -> Capabilities:
        cache_key = f"{crs}:{version}"
        cached = self.capabilities_cache.get(cache_key)
        if cached:
            return cached
        base_url = self.resolve_base_url(crs)
        query = f"{base_url}?{urlencode(CAPABILITIES_QUERY)}"
        logger.debug("Fetching GIBS capabilities: url=%s", query)
        request = Request(query, headers={"User-Agent": self.user_agent})
        try:
            with urlopen(request, timeout=self.timeout_s) as response:
                xml_payload = response.read()
        except (HTTPError, URLError, TimeoutError) as exc:
            raise GIBSRequestError(f"Failed to fetch GetCapabilities: {exc}") from exc
        capabilities = self.parse_capabilities(xml_payload)
        self.capabilities_cache.set(cache_key, capabilities)
        return capabilities

    # -------------------------------------------------------------------------
    def build_capability_candidates(self, requested_crs: str, layer: str) -> list[str]:
        requested = requested_crs.upper()
        candidates: list[str] = [requested]
        for fallback in ("EPSG:3857", "EPSG:4326"):
            if fallback in self.wms_base_endpoints and fallback not in candidates:
                candidates.append(fallback)
        for crs in self.wms_base_endpoints:
            normalized = crs.upper()
            if normalized not in candidates:
                candidates.append(normalized)
        return candidates

    # -------------------------------------------------------------------------
    def resolve_capabilities_for_layer(
        self, *, requested_crs: str, layer: str, wms_version: str
    ) -> tuple[Capabilities, str]:
        errors: list[str] = []
        for candidate in self.build_capability_candidates(requested_crs, layer):
            try:
                capabilities = self.load_capabilities(candidate, wms_version)
            except GIBSRequestError as exc:
                errors.append(f"{candidate}:{exc}")
                continue
            if layer in capabilities.layers:
                return capabilities, candidate
        detail = "; ".join(errors) if errors else "layer not advertised"
        raise GIBSValidationError(
            f"Layer '{layer}' not available for CRS '{requested_crs}'. ({detail})"
        )

    # -------------------------------------------------------------------------
    def resolve_base_url(self, crs: str) -> str:
        key = crs.upper()
        base_url = self.wms_base_endpoints.get(key)
        if not base_url:
            raise GIBSValidationError(f"No WMS endpoint configured for '{crs}'.")
        return base_url

    # -------------------------------------------------------------------------
    def parse_capabilities(self, payload: bytes) -> Capabilities:
        try:
            document = ElementTree.fromstring(payload)
        except ElementTree.ParseError as exc:
            raise GIBSRequestError(
                f"Unable to parse GetCapabilities XML: {exc}"
            ) from exc
        namespace = self.detect_namespace(document)
        request_formats = self.extract_request_formats(document, namespace)
        layers = self.extract_layers(document, namespace)
        return Capabilities(
            layers=layers,
            supported_formats=frozenset(request_formats),
            retrieved_at=time.time(),
        )

    # -------------------------------------------------------------------------
    def detect_namespace(self, document: ElementTree.Element) -> str:
        if document.tag.startswith("{"):
            namespace = document.tag.split("}")[0].strip("{")
            return f"{{{namespace}}}"
        return ""

    # -------------------------------------------------------------------------
    def extract_request_formats(
        self, document: ElementTree.Element, namespace: str
    ) -> set[str]:
        formats: set[str] = set()
        get_map_path = f".//{namespace}Request/{namespace}GetMap/{namespace}Format"
        for node in document.findall(get_map_path):
            if node.text:
                formats.add(node.text.strip().lower())
        return formats

    # -------------------------------------------------------------------------
    def extract_layers(
        self, document: ElementTree.Element, namespace: str
    ) -> LayerStore:
        capability = document.find(f"{namespace}Capability")
        if capability is None:
            raise GIBSRequestError("Capabilities document missing Capability element.")
        root_layer = capability.find(f"{namespace}Layer")
        if root_layer is None:
            raise GIBSRequestError("Capabilities document missing Layer element.")
        layers: LayerStore = {}
        self.walk_layers(
            layer=root_layer,
            namespace=namespace,
            accumulator=layers,
            inherited_crs=set(),
            inherited_formats=set(),
            inherited_time=None,
        )
        if not layers:
            raise GIBSRequestError("Capabilities document does not expose any layers.")
        return layers

    # -------------------------------------------------------------------------
    def walk_layers(
        self,
        *,
        layer: ElementTree.Element,
        namespace: str,
        accumulator: LayerStore,
        inherited_crs: set[str],
        inherited_formats: set[str],
        inherited_time: str | None,
    ) -> None:
        local_crs = set(inherited_crs)
        for node in layer.findall(f"{namespace}CRS"):
            if node.text:
                local_crs.add(node.text.strip().upper())
        local_formats = set(inherited_formats)
        for node in layer.findall(f"{namespace}Format"):
            if node.text:
                local_formats.add(node.text.strip().lower())
        time_extent = self.extract_time_extent(layer, namespace) or inherited_time
        name_node = layer.find(f"{namespace}Name")
        if name_node is not None and name_node.text:
            name = name_node.text.strip()
            metadata = LayerMetadata(
                name=name,
                supported_crs=frozenset(local_crs),
                formats=frozenset(local_formats),
                time_extent=time_extent,
            )
            accumulator[name] = metadata
        for child in layer.findall(f"{namespace}Layer"):
            self.walk_layers(
                layer=child,
                namespace=namespace,
                accumulator=accumulator,
                inherited_crs=local_crs,
                inherited_formats=local_formats,
                inherited_time=time_extent,
            )

    # -------------------------------------------------------------------------
    def extract_time_extent(
        self, layer: ElementTree.Element, namespace: str
    ) -> str | None:
        targets = [
            f"{namespace}Dimension[@name='time']",
            f"{namespace}Extent[@name='time']",
        ]
        for path in targets:
            node = layer.find(path)
            if node is not None and node.text:
                return node.text.strip()
        return None

    # -------------------------------------------------------------------------
    def extract_layer(self, name: str, capabilities: Capabilities) -> LayerMetadata:
        try:
            return capabilities.layers[name]
        except KeyError as exc:
            raise GIBSValidationError(
                f"Layer '{name}' not found in capabilities."
            ) from exc

    # -------------------------------------------------------------------------
    def resolve_layer_crs(self, metadata: LayerMetadata, requested_crs: str) -> str:
        supported = metadata.supported_crs or frozenset({"EPSG:3857"})
        if requested_crs in supported:
            return requested_crs
        if "EPSG:3857" in supported:
            return "EPSG:3857"
        if "EPSG:4326" in supported:
            return "EPSG:4326"
        raise GIBSValidationError(
            f"Layer '{metadata.name}' not available in requested CRS '{requested_crs}'."
        )

    # -------------------------------------------------------------------------
    def validate_format(
        self,
        format_value: str,
        metadata: LayerMetadata,
        capabilities: Capabilities,
    ) -> None:
        allowed_formats = metadata.formats or capabilities.supported_formats
        if allowed_formats and format_value not in allowed_formats:
            raise GIBSValidationError(
                f"Format '{format_value}' is not supported for layer '{metadata.name}'."
            )

    # -------------------------------------------------------------------------
    def parse_imagery_date(self, imagery_date: str) -> date:
        try:
            return date.fromisoformat(imagery_date)
        except ValueError as exc:
            raise GIBSValidationError(
                "Imagery date must follow ISO format YYYY-MM-DD."
            ) from exc

    # -------------------------------------------------------------------------
    def parse_time_extent(self, time_extent: str) -> tuple[date | None, date | None]:
        expressions = [expr.strip() for expr in time_extent.split(",") if expr.strip()]
        min_supported: date | None = None
        max_supported: date | None = None
        for expression in expressions:
            if "/" in expression:
                parts = expression.split("/")
                if len(parts) >= 2:
                    start = self.safe_parse_date(parts[0])
                    end = self.safe_parse_date(parts[1])
                    if start and (min_supported is None or start < min_supported):
                        min_supported = start
                    if end and (max_supported is None or end > max_supported):
                        max_supported = end
            else:
                literal = self.safe_parse_date(expression)
                if literal:
                    if min_supported is None or literal < min_supported:
                        min_supported = literal
                    if max_supported is None or literal > max_supported:
                        max_supported = literal
        return min_supported, max_supported

    # -------------------------------------------------------------------------
    def resolve_supported_imagery_date(
        self, imagery_date: date, metadata: LayerMetadata
    ) -> date:
        if not metadata.time_extent:
            return imagery_date
        min_supported, max_supported = self.parse_time_extent(metadata.time_extent)
        if min_supported and imagery_date < min_supported:
            return min_supported
        if max_supported and imagery_date > max_supported:
            return max_supported
        return imagery_date

    # -------------------------------------------------------------------------
    def resolve_request_dates(self, *, layer: str, imagery_date: date) -> list[date]:
        fallback_days = self.layer_date_fallback_days.get(layer, 0)
        return [
            imagery_date - timedelta(days=offset) for offset in range(fallback_days + 1)
        ]

    # -------------------------------------------------------------------------
    def should_retry_previous_date(
        self, *, layer: str, error: GIBSRequestError
    ) -> bool:
        if self.layer_date_fallback_days.get(layer, 0) <= 0:
            return False
        message = str(error).lower()
        return (
            "gibs getmap returned non image payload" in message
            or "shapefile cannot be found" in message
            or "failed to draw layer named" in message
        )

    # -------------------------------------------------------------------------
    def ensure_layer_temporal_support(
        self, imagery_date: date, metadata: LayerMetadata
    ) -> None:
        if not metadata.time_extent:
            return
        min_supported, max_supported = self.parse_time_extent(metadata.time_extent)
        if min_supported and imagery_date < min_supported:
            raise GIBSValidationError(
                (
                    f"Layer '{metadata.name}' supports imagery starting "
                    f"{min_supported.isoformat()}; requested {imagery_date.isoformat()}."
                )
            )
        if max_supported and imagery_date > max_supported:
            raise GIBSValidationError(
                (
                    f"Layer '{metadata.name}' supports imagery through "
                    f"{max_supported.isoformat()}; requested {imagery_date.isoformat()}."
                )
            )
        if min_supported or max_supported:
            return
        raise GIBSValidationError(
            f"No imagery for '{metadata.name}' on {imagery_date.isoformat()}."
        )

    # -------------------------------------------------------------------------
    def safe_parse_date(self, value: str) -> date | None:
        normalized = (value or "").strip()
        if not normalized:
            return None
        lowered = normalized.lower()
        if lowered in {"present", "now", "latest"}:
            return date.today()
        try:
            return date.fromisoformat(normalized)
        except ValueError:
            return None

    # -------------------------------------------------------------------------
    def build_query(
        self,
        *,
        base_url: str,
        bbox: BBox,
        crs: str,
        width: int,
        height: int,
        layer: str,
        imagery_date: str,
        format_value: str,
        style_value: str,
        wms_version: str,
    ) -> str:
        bbox_payload = self.format_bbox(bbox, crs, wms_version)
        params = {
            "SERVICE": "WMS",
            "REQUEST": "GetMap",
            "VERSION": wms_version,
            "LAYERS": layer,
            "CRS": crs,
            "STYLES": style_value,
            "BBOX": bbox_payload,
            "WIDTH": str(width),
            "HEIGHT": str(height),
            "FORMAT": format_value,
            "TIME": imagery_date,
        }
        query = urlencode(params, safe=",")
        return f"{base_url}?{query}"

    # -------------------------------------------------------------------------
    def format_bbox(self, bbox: BBox, crs: str, version: str) -> str:
        minx, miny, maxx, maxy = bbox
        if crs == "EPSG:4326" and version == "1.3.0":
            values = (miny, minx, maxy, maxx)
        else:
            values = (minx, miny, maxx, maxy)
        return ",".join(f"{value:.{self.bbox_precision}f}" for value in values)

    # -------------------------------------------------------------------------
    def execute_request(self, url: str, timeout_s: int) -> tuple[bytes, str, str]:
        max_attempts = 3
        for attempt in range(max_attempts):
            request = Request(
                url,
                headers={
                    "User-Agent": self.user_agent,
                    "Accept": "image/png,image/jpeg",
                },
            )
            try:
                with urlopen(request, timeout=timeout_s) as response:
                    content_type = (response.headers.get("Content-Type") or "").split(
                        ";", 1
                    )[0]
                    payload = response.read()
                    if not content_type.startswith("image/"):
                        message = payload.decode("utf-8", errors="ignore")
                        raise GIBSRequestError(
                            f"GIBS GetMap returned non image payload: {message[:200]}"
                        )
                    if len(payload) < 1024:
                        raise GIBSRequestError(
                            "GIBS GetMap returned a suspiciously small payload."
                        )
                    declared_length = self.extract_content_length(response.headers)
                    self.ensure_payload_integrity(
                        payload, content_type, declared_length
                    )
                    logger.info("Fetched GIBS image: url=%s size=%s", url, len(payload))
                    return payload, content_type, url
            except GIBSPayloadIntegrityError:
                if attempt < max_attempts - 1:
                    time.sleep(self.compute_backoff_delay(attempt))
                    continue
                raise
            except HTTPError as exc:
                if 500 <= exc.code < 600 and attempt < max_attempts - 1:
                    time.sleep(self.compute_backoff_delay(attempt))
                    continue
                raise GIBSRequestError(f"GIBS GetMap failed: HTTP {exc.code}") from exc
            except (URLError, TimeoutError) as exc:
                if attempt < max_attempts - 1:
                    time.sleep(self.compute_backoff_delay(attempt))
                    continue
                raise GIBSRequestError(f"GIBS GetMap failed: {exc}") from exc
        raise GIBSRequestError("GIBS GetMap failed after retries.")

    # -------------------------------------------------------------------------
    def extract_content_length(self, headers: Any) -> int | None:
        value = headers.get("Content-Length")
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    # -------------------------------------------------------------------------
    def ensure_payload_integrity(
        self, payload: bytes, content_type: str, declared_length: int | None
    ) -> None:
        if declared_length is not None and len(payload) < declared_length:
            raise GIBSPayloadIntegrityError(
                "GIBS GetMap payload shorter than declared Content-Length."
            )
        if content_type == "image/png" and not self.png_has_terminal_chunk(payload):
            raise GIBSPayloadIntegrityError(
                "GIBS GetMap returned PNG missing terminal IEND chunk."
            )

    # -------------------------------------------------------------------------
    def png_has_terminal_chunk(self, payload: bytes) -> bool:
        if len(payload) < 12:
            return False
        png_signature = b"\x89PNG\r\n\x1a\n"
        if payload.startswith(png_signature) and payload.endswith(
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        ):
            return True
        return not payload.startswith(png_signature)

    # -------------------------------------------------------------------------
    def compute_backoff_delay(self, attempt: int) -> float:
        return self.retry_backoff_s * (2**attempt)

    # -------------------------------------------------------------------------
    def lonlat_to_mercator(self, lon: float, lat: float) -> tuple[float, float]:
        lon_clamped = clamp(lon, MIN_LONGITUDE, MAX_LONGITUDE)
        lat_clamped = clamp(lat, MIN_MERCATOR_LAT, MAX_MERCATOR_LAT)
        x = (lon_clamped * ORIGIN_SHIFT) / 180.0
        rad = math.radians(lat_clamped)
        y = math.log(math.tan((math.pi / 4.0) + (rad / 2.0))) * ORIGIN_SHIFT / math.pi
        return x, y

    # -------------------------------------------------------------------------
    def compute_geographic_bbox(self, lon: float, lat: float, radius_m: float) -> BBox:
        lat_clamped = clamp(lat, MIN_GEO_LAT, MAX_GEO_LAT)
        lat_rad = math.radians(lat_clamped)
        cos_lat = math.cos(lat_rad)
        if abs(cos_lat) < 1e-6:
            cos_lat = 1e-6 if cos_lat >= 0 else -1e-6
        d_lat = (radius_m / EARTH_RADIUS_M) * (180.0 / math.pi)
        d_lon = (radius_m / (EARTH_RADIUS_M * cos_lat)) * (180.0 / math.pi)
        min_lon = clamp(lon - d_lon, MIN_LONGITUDE, MAX_LONGITUDE)
        max_lon = clamp(lon + d_lon, MIN_LONGITUDE, MAX_LONGITUDE)
        min_lat = clamp(lat_clamped - d_lat, MIN_GEO_LAT, MAX_GEO_LAT)
        max_lat = clamp(lat_clamped + d_lat, MIN_GEO_LAT, MAX_GEO_LAT)
        return [min_lon, min_lat, max_lon, max_lat]

    # -------------------------------------------------------------------------
    def bbox_span_in_meters(self, bbox: BBox, crs: str) -> tuple[float, float]:
        if crs == "EPSG:3857":
            min_x, min_y, max_x, max_y = bbox
            return abs(max_x - min_x), abs(max_y - min_y)
        if crs == "EPSG:4326":
            min_lon, min_lat, max_lon, max_lat = bbox
            min_x, min_y = self.lonlat_to_mercator(min_lon, min_lat)
            max_x, max_y = self.lonlat_to_mercator(max_lon, max_lat)
            return abs(max_x - min_x), abs(max_y - min_y)
        raise GIBSValidationError(f"Unable to compute bbox span for '{crs}'.")

    # -------------------------------------------------------------------------
    def compute_meters_per_pixel(
        self, bbox: BBox, crs: str, width: int, height: int
    ) -> dict[str, float]:
        span_x, span_y = self.bbox_span_in_meters(bbox, crs)
        return {
            "x": span_x / float(width),
            "y": span_y / float(height),
        }

    # -------------------------------------------------------------------------
    def ensure_bbox_resolution(
        self, layer: str, bbox: BBox, crs: str, width: int, height: int
    ) -> BBox:
        meters_per_pixel = self.resolve_layer_meters_per_pixel(layer)
        if not meters_per_pixel:
            return bbox
        target_meter_span = max(meters_per_pixel)
        span_x, span_y = self.bbox_span_in_meters(bbox, crs)
        min_span_x = target_meter_span * float(width)
        min_span_y = target_meter_span * float(height)
        if span_x >= min_span_x and span_y >= min_span_y:
            return bbox
        return self.expand_bbox_to_span(bbox, crs, min_span_x, min_span_y)

    # -------------------------------------------------------------------------
    def expand_bbox_to_span(
        self, bbox: BBox, crs: str, span_x_m: float, span_y_m: float
    ) -> BBox:
        min_x, min_y, max_x, max_y = bbox
        if crs == "EPSG:3857":
            center_x = (min_x + max_x) / 2.0
            center_y = (min_y + max_y) / 2.0
            half_span_x = span_x_m / 2.0
            half_span_y = span_y_m / 2.0
            expanded_bbox = [
                center_x - half_span_x,
                center_y - half_span_y,
                center_x + half_span_x,
                center_y + half_span_y,
            ]
            self.validate_bbox_values(expanded_bbox, crs)
            return expanded_bbox
        if crs == "EPSG:4326":
            center_lon = (min_x + max_x) / 2.0
            center_lat = (min_y + max_y) / 2.0
            center_x, center_y = self.lonlat_to_mercator(center_lon, center_lat)
            half_span_x = span_x_m / 2.0
            half_span_y = span_y_m / 2.0
            expanded_mercator = [
                center_x - half_span_x,
                center_y - half_span_y,
                center_x + half_span_x,
                center_y + half_span_y,
            ]
            expanded = self.reproject_bbox(expanded_mercator, "EPSG:4326")
            self.validate_bbox_values(expanded, crs)
            return expanded
        raise GIBSValidationError(f"Unable to expand bbox for '{crs}'.")

    # -------------------------------------------------------------------------
    def reproject_bbox(self, bbox: BBox, target_crs: str) -> BBox:
        if target_crs == "EPSG:3857":
            min_lon, min_lat, max_lon, max_lat = bbox
            min_x, min_y = self.lonlat_to_mercator(min_lon, min_lat)
            max_x, max_y = self.lonlat_to_mercator(max_lon, max_lat)
            return [min_x, min_y, max_x, max_y]
        if target_crs == "EPSG:4326":
            min_x, min_y, max_x, max_y = bbox
            min_lon, min_lat = self.mercator_to_lonlat(min_x, min_y)
            max_lon, max_lat = self.mercator_to_lonlat(max_x, max_y)
            return [min_lon, min_lat, max_lon, max_lat]
        raise GIBSValidationError(f"Unable to reproject bbox to '{target_crs}'.")

    # -------------------------------------------------------------------------
    def resolve_effective_radius(self, radius_m: float | None) -> float:
        base = radius_m if radius_m and radius_m > 0 else 2500.0
        return max(base, self.min_visual_radius_m)

    # -------------------------------------------------------------------------
    def normalize_style(self, style: str | None) -> str:
        if not style:
            return "default"
        normalized = str(style).strip()
        return normalized or "default"

    # -------------------------------------------------------------------------
    def mercator_to_lonlat(self, x: float, y: float) -> tuple[float, float]:
        lon = (x / ORIGIN_SHIFT) * 180.0
        lat = (y / ORIGIN_SHIFT) * 180.0
        lat = (
            180.0
            / math.pi
            * (2.0 * math.atan(math.exp(lat * math.pi / 180.0)) - math.pi / 2.0)
        )
        return lon, lat

    # -------------------------------------------------------------------------
    def validate_dimensions(self, width: int, height: int) -> None:
        if not (GIBS_MIN_IMAGE_DIMENSION <= width <= GIBS_MAX_IMAGE_DIMENSION):
            raise GIBSValidationError(
                f"Width must be between {GIBS_MIN_IMAGE_DIMENSION} and {GIBS_MAX_IMAGE_DIMENSION} pixels."
            )
        if not (GIBS_MIN_IMAGE_DIMENSION <= height <= GIBS_MAX_IMAGE_DIMENSION):
            raise GIBSValidationError(
                f"Height must be between {GIBS_MIN_IMAGE_DIMENSION} and {GIBS_MAX_IMAGE_DIMENSION} pixels."
            )

