from __future__ import annotations

import math
import os
import time
from collections import OrderedDict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode, urljoin
from xml.etree import ElementTree

import httpx
from pyproj import CRS, Transformer

from AEGIS.app.api.schemas.geographics import MapRequest, TemporalContext
from AEGIS.app.api.schemas.gibs import (
    GIBSImageryPayload,
    GIBSLayer,
    GIBSLayerProjection,
    GIBSMapOptions,
    GIBSMatrixSet,
    GIBSRequest,
    GIBSTileCoordinates,
    GIBSTimeDomain,
    ResolvedLocation,
    TemporalParameters,
    TemporalSelection,
    WMTSRequestOptions,
    WMSBoundingBox,
    WMSRequestOptions,
)
from AEGIS.app.api.schemas.gibs import WMTSProjectionCapabilities, WMSProjectionCapabilities


###############################################################################
class TTLCache:
    def __init__(self, ttl_seconds: float, max_entries: int | None = None) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self.values: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> Any | None:
        now = time.time()
        record = self.values.get(key)
        if not record:
            return None
        expires_at, value = record
        if expires_at < now:
            self.values.pop(key, None)
            return None
        self.values.move_to_end(key)
        return value

    def set(self, key: str, value: Any, ttl_override: float | None = None) -> None:
        ttl = ttl_override or self.ttl_seconds
        expires_at = time.time() + ttl
        self.values[key] = (expires_at, value)
        self.values.move_to_end(key)
        if self.max_entries is not None:
            while len(self.values) > self.max_entries:
                self.values.popitem(last=False)


###############################################################################
@dataclass(slots=True)
class GIBSSettings:
    projection_default: str = "epsg3857"
    endpoint_flavor_default: str = "best"
    time_policy: str = "nearest-earlier"
    capabilities_ttl: float = 6 * 3600.0
    domain_ttl: float = 6 * 3600.0
    imagery_ttl: float = 12 * 3600.0
    imagery_cache_size: int = 128
    discovery_timeout: float = 15.0
    imagery_timeout: float = 20.0
    retry_attempts: int = 3
    retry_backoff: float = 1.5
    shard_domains: list[str] = field(
        default_factory=lambda: [
            "gibs.earthdata.nasa.gov",
            "gibs-a.earthdata.nasa.gov",
            "gibs-b.earthdata.nasa.gov",
            "gibs-c.earthdata.nasa.gov",
        ]
    )
    enable_domain_sharding: bool = True
    user_agent: str = "AEGIS-Geographics/2.0"
    today_fallback_window_days: int = 3

    @classmethod
    def from_environment(cls) -> "GIBSSettings":
        env = os.environ
        projection = env.get("GIBS_DEFAULT_PROJECTION", cls.projection_default)
        flavor = env.get("GIBS_ENDPOINT_FLAVOR", cls.endpoint_flavor_default)
        time_policy = env.get("GIBS_TIME_POLICY", cls.time_policy)
        sharding_toggle = env.get("GIBS_SHARDING_ENABLED")
        enable_sharding = cls.enable_domain_sharding
        if sharding_toggle is not None:
            enable_sharding = sharding_toggle.strip().lower() not in {"0", "false"}
        shards = env.get("GIBS_SHARDS")
        if shards:
            shard_list = [piece.strip() for piece in shards.split(",") if piece.strip()]
        else:
            shard_list = cls().shard_domains
        return cls(
            projection_default=projection.strip().lower(),
            endpoint_flavor_default=flavor.strip().lower(),
            time_policy=time_policy.strip().lower(),
            shard_domains=shard_list,
            enable_domain_sharding=enable_sharding,
        )


###############################################################################
def parse_iso_datetime(value: str) -> datetime:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Empty time value")
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError as exc:
        raise ValueError(f"Invalid ISO-8601 time: {value}") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=None)
    return parsed.astimezone(tz=None)


###############################################################################
def parse_iso_date(value: str) -> datetime:
    cleaned = value.strip()
    try:
        parsed_date = datetime.fromisoformat(cleaned)
    except ValueError as exc:
        raise ValueError(f"Invalid ISO date value: {value}") from exc
    if parsed_date.tzinfo is not None:
        return parsed_date.astimezone(tz=None)
    return parsed_date


###############################################################################
def parse_duration(value: str) -> timedelta:
    if not value or not value.startswith("P"):
        raise ValueError(f"Unsupported ISO duration: {value}")
    time_part = value[1:]
    days = hours = minutes = seconds = 0
    if "T" in time_part:
        date_part, time_part = time_part.split("T", 1)
    else:
        date_part, time_part = time_part, ""
    if date_part:
        if date_part.endswith("D"):
            days = int(date_part[:-1] or "0")
        elif date_part.endswith("Y"):
            days = int(date_part[:-1] or "0") * 365
        elif date_part.endswith("M"):
            days = int(date_part[:-1] or "0") * 30
    if time_part:
        if time_part.endswith("S"):
            seconds = int(time_part[:-1] or "0")
        elif time_part.endswith("M"):
            minutes = int(time_part[:-1] or "0")
        elif time_part.endswith("H"):
            hours = int(time_part[:-1] or "0")
    return timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)


###############################################################################
def expand_time_values(raw_values: Iterable[str]) -> list[str]:
    expanded: list[str] = []
    for item in raw_values:
        piece = item.strip()
        if not piece:
            continue
        if "/" not in piece:
            expanded.append(piece)
            continue
        start_text, end_text, step_text = piece.split("/")
        start_dt = parse_iso_datetime(start_text)
        end_dt = parse_iso_datetime(end_text)
        step = parse_duration(step_text)
        if step.total_seconds() <= 0:
            expanded.append(start_text)
            continue
        current = start_dt
        while current <= end_dt:
            expanded.append(current.strftime("%Y-%m-%dT%H:%M:%SZ"))
            current += step
    return expanded


###############################################################################
def normalize_projection(value: str) -> str:
    cleaned = value.strip().lower()
    if cleaned.startswith("epsg:"):
        cleaned = cleaned.replace("epsg:", "epsg")
    return cleaned


###############################################################################
def normalize_flavor(value: str) -> str:
    lowered = value.strip().lower()
    if lowered not in {"best", "std", "nrt", "all"}:
        return "best"
    return lowered


###############################################################################
class GIBSTimeResolver:
    def __init__(self, settings: GIBSSettings) -> None:
        self.settings = settings

    def resolve(
        self,
        requested: str | None,
        domain: GIBSTimeDomain | None,
        default_candidate: str | None,
    ) -> TemporalSelection:
        if requested:
            try:
                target = parse_iso_datetime(requested)
            except ValueError:
                target = parse_iso_date(requested)
        else:
            target = None
        if domain is None or not domain.values:
            if requested:
                return TemporalSelection(iso_value=requested)
            if default_candidate:
                return TemporalSelection(iso_value=default_candidate)
            today = date.today()
            return TemporalSelection(iso_value=today.isoformat())
        available_values = domain.sorted_values()
        parsed_values = [parse_iso_datetime(value) for value in available_values]
        if target is None:
            if domain.default:
                return TemporalSelection(iso_value=domain.default)
            latest = max(parsed_values)
            return TemporalSelection(iso_value=available_values[parsed_values.index(latest)])
        closest = None
        for candidate, iso_value in zip(parsed_values, available_values):
            if candidate > target:
                break
            closest = (candidate, iso_value)
        if closest and self.settings.time_policy in {"nearest-earlier", "default"}:
            reason = None
            if closest[0] != target:
                reason = "Requested time unavailable; snapped to nearest earlier value."
            return TemporalSelection(iso_value=closest[1], snapped=bool(reason), reason=reason)
        if closest is None:
            earliest = min(parsed_values)
            return TemporalSelection(
                iso_value=available_values[parsed_values.index(earliest)],
                snapped=True,
                reason="Requested time precedes available range; using earliest value.",
            )
        return TemporalSelection(iso_value=requested)

    def fallback_today(self, domain: GIBSTimeDomain | None) -> TemporalSelection | None:
        if domain is None or not domain.values:
            return None
        today = datetime.now(timezone.utc)
        parsed_pairs = []
        for iso_value in domain.sorted_values():
            candidate = parse_iso_datetime(iso_value)
            if candidate.tzinfo is None:
                candidate = candidate.replace(tzinfo=timezone.utc)
            else:
                candidate = candidate.astimezone(timezone.utc)
            parsed_pairs.append((candidate, iso_value))
        parsed_pairs.sort(key=lambda item: item[0])
        closest = None
        for candidate, iso_value in parsed_pairs:
            if candidate <= today:
                closest = (candidate, iso_value)
        if closest is None:
            return None
        if (today - closest[0]).days <= self.settings.today_fallback_window_days:
            return TemporalSelection(
                iso_value=closest[1],
                snapped=True,
                reason="Latest imagery used because current day is not yet available.",
            )
        return None


###############################################################################
class ProjectionTransformers:
    def __init__(self) -> None:
        self.transformers: dict[tuple[str, str], Transformer] = {}

    def to_projection(self, projection: str) -> Transformer:
        key = ("epsg:4326", projection)
        if key not in self.transformers:
            source = CRS.from_epsg(4326)
            target_code = projection.replace("epsg", "EPSG:")
            target = CRS.from_string(target_code)
            self.transformers[key] = Transformer.from_crs(
                source, target, always_xy=True
            )
        return self.transformers[key]

    def from_projection(self, projection: str) -> Transformer:
        key = (projection, "epsg:4326")
        if key not in self.transformers:
            source_code = projection.replace("epsg", "EPSG:")
            source = CRS.from_string(source_code)
            target = CRS.from_epsg(4326)
            self.transformers[key] = Transformer.from_crs(
                source, target, always_xy=True
            )
        return self.transformers[key]


###############################################################################
class WMTSMatrixCalculator:
    def __init__(self, matrix_set: GIBSMatrixSet, projection: str, transformers: ProjectionTransformers) -> None:
        self.matrix_set = matrix_set
        self.projection = projection
        self.transformer = transformers.to_projection(projection)

    def compute_tile(self, latitude: float, longitude: float, tile_matrix: str | None) -> GIBSTileCoordinates:
        zoom_levels = self.matrix_set.levels
        if tile_matrix is None:
            tile_matrix = zoom_levels[-1]
        if tile_matrix not in zoom_levels:
            raise ValueError(
                f"TileMatrix {tile_matrix} is not valid for matrix set {self.matrix_set.identifier}."
            )
        index = zoom_levels.index(tile_matrix)
        scale = self.matrix_set.scale_denominators[index]
        resolution = scale * 0.00028
        top_left_x, top_left_y = self.matrix_set.top_left_corner
        tile_width_m = self.matrix_set.tile_width * resolution
        tile_height_m = self.matrix_set.tile_height * resolution
        x, y = self.transformer.transform(longitude, latitude)
        column = int((x - top_left_x) / tile_width_m)
        row = int((top_left_y - y) / tile_height_m)
        matrix_width = self.matrix_set.matrix_widths[index]
        matrix_height = self.matrix_set.matrix_heights[index]
        column = max(0, min(column, matrix_width - 1))
        row = max(0, min(row, matrix_height - 1))
        zoom_value = index
        try:
            zoom_value = int(tile_matrix.split("_")[-1])
        except ValueError:
            zoom_value = index
        return GIBSTileCoordinates(
            zoom=zoom_value,
            column=column,
            row=row,
            tile_matrix=tile_matrix,
            tile_matrix_set=self.matrix_set.identifier,
        )


###############################################################################
class WMTS3857Calculator(WMTSMatrixCalculator):
    def compute_tile(self, latitude: float, longitude: float, tile_matrix: str | None) -> GIBSTileCoordinates:
        zoom_levels = self.matrix_set.levels
        if tile_matrix is None:
            tile_matrix = zoom_levels[-1]
        if tile_matrix not in zoom_levels:
            raise ValueError(
                f"TileMatrix {tile_matrix} is not valid for matrix set {self.matrix_set.identifier}."
            )
        index = zoom_levels.index(tile_matrix)
        zoom_level = index
        try:
            zoom_level = int(tile_matrix.split("_")[-1])
        except ValueError:
            zoom_level = index
        lat_rad = math.radians(latitude)
        n = 2**zoom_level
        x_tile = (longitude + 180.0) / 360.0 * n
        y_tile = (
            (1.0 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2.0 * n
        )
        column = int(min(max(x_tile, 0.0), n - 1))
        row = int(min(max(y_tile, 0.0), n - 1))
        return GIBSTileCoordinates(
            zoom=zoom_level,
            column=column,
            row=row,
            tile_matrix=tile_matrix,
            tile_matrix_set=self.matrix_set.identifier,
        )


###############################################################################
class CapabilitiesParser:
    WMTS_NS = {
        "wmts": "http://www.opengis.net/wmts/1.0",
        "ows": "http://www.opengis.net/ows/1.1",
    }
    WMS_NS = {
        "wms": "http://www.opengis.net/wms",
        "xlink": "http://www.w3.org/1999/xlink",
    }

    def parse_wmts(self, xml_text: str) -> tuple[dict[str, GIBSLayer], dict[str, GIBSMatrixSet]]:
        tree = ElementTree.fromstring(xml_text)
        layers: dict[str, GIBSLayer] = {}
        matrix_sets: dict[str, GIBSMatrixSet] = {}
        for matrix_node in tree.findall(".//wmts:TileMatrixSet", self.WMTS_NS):
            identifier = matrix_node.findtext("ows:Identifier", default="", namespaces=self.WMTS_NS)
            if not identifier:
                continue
            matrix_projection_text = matrix_node.findtext("ows:SupportedCRS", namespaces=self.WMTS_NS)
            if not matrix_projection_text:
                continue
            matrix_projection = normalize_projection(matrix_projection_text)
            tile_width = int(matrix_node.findtext("wmts:TileWidth", default="256", namespaces=self.WMTS_NS))
            tile_height = int(matrix_node.findtext("wmts:TileHeight", default="256", namespaces=self.WMTS_NS))
            top_left_text = matrix_node.findtext("wmts:TopLeftCorner", namespaces=self.WMTS_NS)
            if top_left_text:
                left_x, top_y = [float(value) for value in top_left_text.split()]
            else:
                left_x, top_y = -180.0, 90.0
            levels: list[str] = []
            scales: list[float] = []
            matrix_widths: list[int] = []
            matrix_heights: list[int] = []
            for tile_matrix in matrix_node.findall("wmts:TileMatrix", self.WMTS_NS):
                level_id = tile_matrix.findtext("ows:Identifier", namespaces=self.WMTS_NS)
                if level_id is None:
                    continue
                levels.append(level_id)
                scale_text = tile_matrix.findtext("wmts:ScaleDenominator", namespaces=self.WMTS_NS)
                matrix_width_text = tile_matrix.findtext("wmts:MatrixWidth", namespaces=self.WMTS_NS)
                matrix_height_text = tile_matrix.findtext("wmts:MatrixHeight", namespaces=self.WMTS_NS)
                scales.append(float(scale_text or 1.0))
                matrix_widths.append(int(matrix_width_text or "1"))
                matrix_heights.append(int(matrix_height_text or "1"))
            matrix_sets[identifier] = GIBSMatrixSet(
                identifier=identifier,
                projection=matrix_projection,
                tile_width=tile_width,
                tile_height=tile_height,
                top_left_corner=(left_x, top_y),
                scale_denominators=scales,
                matrix_widths=matrix_widths,
                matrix_heights=matrix_heights,
                levels=levels,
            )
        for layer_node in tree.findall(".//wmts:Layer", self.WMTS_NS):
            identifier = layer_node.findtext("ows:Identifier", namespaces=self.WMTS_NS)
            if not identifier:
                continue
            title = layer_node.findtext("ows:Title", namespaces=self.WMTS_NS) or identifier
            formats = [
                format_node.text
                for format_node in layer_node.findall("wmts:Format", self.WMTS_NS)
                if format_node.text
            ]
            styles = [
                style.findtext("ows:Identifier", namespaces=self.WMTS_NS) or "default"
                for style in layer_node.findall("wmts:Style", self.WMTS_NS)
            ]
            matrix_links = [
                link.findtext("wmts:TileMatrixSet", namespaces=self.WMTS_NS)
                for link in layer_node.findall("wmts:TileMatrixSetLink", self.WMTS_NS)
            ]
            matrix_links = [link for link in matrix_links if link]
            dimension_node = layer_node.find("wmts:Dimension", self.WMTS_NS)
            time_domain = None
            if dimension_node is not None:
                identifier_text = dimension_node.findtext("ows:Identifier", namespaces=self.WMTS_NS)
                if identifier_text and identifier_text.lower() == "time":
                    default_value = dimension_node.findtext("wmts:Default", namespaces=self.WMTS_NS)
                    current_text = dimension_node.findtext("wmts:Current", namespaces=self.WMTS_NS)
                    time_values = [
                        value.text for value in dimension_node.findall("wmts:Value", self.WMTS_NS)
                        if value.text
                    ]
                    limited = len(time_values) >= 100
                    time_domain = GIBSTimeDomain(
                        default=default_value,
                        current=(current_text or "false").lower() == "true",
                        values=time_values,
                        limited=limited,
                    )
            projection_key = "unknown"
            for link in matrix_links:
                matrix = matrix_sets.get(link)
                if matrix:
                    projection_key = matrix.projection
                    break
            projection = normalize_projection(projection_key)
            layer_projection = GIBSLayerProjection(
                projection=projection,
                styles=styles or ["default"],
                formats=formats,
                time_supported=time_domain is not None,
                wmts=WMTSProjectionCapabilities(
                    matrix_sets=matrix_links,
                    formats=formats,
                    styles=styles or ["default"],
                    time_domains={link: time_domain for link in matrix_links if time_domain},
                ),
            )
            layer = GIBSLayer(identifier=identifier, title=title, projections={projection: layer_projection})
            layers[identifier] = layer
        return layers, matrix_sets

    def parse_wms(self, xml_text: str, version: str) -> dict[str, GIBSLayer]:
        tree = ElementTree.fromstring(xml_text)
        capability = tree.find("Capability")
        if capability is None:
            return {}
        get_map_formats = [
            fmt.text for fmt in capability.findall("Request/GetMap/Format") if fmt.text
        ]
        layers: dict[str, GIBSLayer] = {}
        for layer_node in capability.findall("Layer/Layer"):
            name = layer_node.findtext("Name")
            title = layer_node.findtext("Title") or (name or "")
            if not name:
                continue
            projections = [
                crs_node.text.strip().lower()
                for crs_node in layer_node.findall("CRS")
                if crs_node.text
            ]
            if not projections:
                projections = [
                    srs_node.text.strip().lower()
                    for srs_node in layer_node.findall("SRS")
                    if srs_node.text
                ]
            styles = [
                style.findtext("Name") or "default"
                for style in layer_node.findall("Style")
            ]
            extent_node = layer_node.find("Dimension[@name='time']")
            if extent_node is None:
                extent_node = layer_node.find("Extent[@name='time']")
            time_domain = None
            nearest = False
            if extent_node is not None and extent_node.text:
                values = expand_time_values(extent_node.text.split(","))
                default_value = extent_node.get("default")
                nearest = extent_node.get("nearestValue", "0") == "1"
                time_domain = GIBSTimeDomain(
                    default=default_value,
                    values=values,
                    current=False,
                    limited=False,
                )
            layer_entry = layers.setdefault(
                name, GIBSLayer(identifier=name, title=title, projections={})
            )
            for projection in projections:
                projection_key = normalize_projection(projection)
                capabilities = WMSProjectionCapabilities(
                    versions=[version],
                    formats=get_map_formats,
                    styles=styles or ["default"],
                    time_domain=time_domain,
                    nearest_value=nearest,
                )
                existing_projection = layer_entry.projections.get(projection_key)
                if existing_projection is not None:
                    merged_styles = sorted({*existing_projection.styles, *(styles or ["default"])})
                    merged_formats = sorted({*existing_projection.formats, *get_map_formats})
                    existing_projection.styles = merged_styles
                    existing_projection.formats = merged_formats
                    existing_projection.time_supported = (
                        existing_projection.time_supported or time_domain is not None
                    )
                    existing_projection.wms[version] = capabilities
                else:
                    layer_entry.projections[projection_key] = GIBSLayerProjection(
                        projection=projection_key,
                        styles=styles or ["default"],
                        formats=get_map_formats,
                        time_supported=time_domain is not None,
                        wms={version: capabilities},
                    )
        return layers


###############################################################################
class GIBSDiscovery:
    WMTS_CAPABILITIES_PATH = "1.0.0/WMTSCapabilities.xml"
    WMTS_KVP = "wmts.cgi"
    WMS_KVP = "wms.cgi"
    WMS_VERSIONS = ["1.3.0", "1.1.1"]

    def __init__(self, settings: GIBSSettings) -> None:
        self.settings = settings
        self.capabilities_cache = TTLCache(settings.capabilities_ttl)
        self.domain_cache = TTLCache(settings.domain_ttl)
        self.parser = CapabilitiesParser()

    def _service_root(self, service: str, projection: str, flavor: str) -> str:
        projection = normalize_projection(projection)
        service = service.lower()
        flavor = normalize_flavor(flavor)
        return f"https://gibs.earthdata.nasa.gov/{service}/{projection}/{flavor}/"

    def _http_get(self, url: str) -> str:
        headers = {"User-Agent": self.settings.user_agent}
        with httpx.Client(timeout=self.settings.discovery_timeout, headers=headers) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.text

    def fetch_wmts(self, projection: str, flavor: str) -> tuple[dict[str, GIBSLayer], dict[str, GIBSMatrixSet]]:
        cache_key = f"wmts:{projection}:{flavor}"
        cached = self.capabilities_cache.get(cache_key)
        if cached:
            return cached
        root = self._service_root("wmts", projection, flavor)
        capabilities_url = urljoin(root, self.WMTS_CAPABILITIES_PATH)
        xml_text = self._http_get(capabilities_url)
        layers, matrix_sets = self.parser.parse_wmts(xml_text)
        self.capabilities_cache.set(cache_key, (layers, matrix_sets))
        return layers, matrix_sets

    def fetch_wms(self, projection: str, flavor: str) -> dict[str, GIBSLayer]:
        cache_key = f"wms:{projection}:{flavor}"
        cached = self.capabilities_cache.get(cache_key)
        if cached:
            return cached
        root = self._service_root("wms", projection, flavor)
        aggregated: dict[str, GIBSLayer] = {}
        for version in self.WMS_VERSIONS:
            params = {"service": "WMS", "request": "GetCapabilities", "version": version}
            url = f"{root}{self.WMS_KVP}?{urlencode(params)}"
            xml_text = self._http_get(url)
            parsed_layers = self.parser.parse_wms(xml_text, version)
            for identifier, layer in parsed_layers.items():
                if identifier not in aggregated:
                    aggregated[identifier] = layer
                else:
                    aggregated_layer = aggregated[identifier]
                    for projection_key, new_projection in layer.projections.items():
                        existing_projection = aggregated_layer.projections.get(projection_key)
                        if existing_projection is None:
                            aggregated_layer.projections[projection_key] = new_projection
                            continue
                        existing_projection.styles = sorted(
                            {*existing_projection.styles, *new_projection.styles}
                        )
                        existing_projection.formats = sorted(
                            {*existing_projection.formats, *new_projection.formats}
                        )
                        existing_projection.time_supported = (
                            existing_projection.time_supported or new_projection.time_supported
                        )
                        for ver, capability in new_projection.wms.items():
                            existing_capability = existing_projection.wms.get(ver)
                            if existing_capability is None:
                                existing_projection.wms[ver] = capability
                                continue
                            existing_capability.versions = sorted(
                                {*existing_capability.versions, *capability.versions}
                            )
                            existing_capability.formats = sorted(
                                {*existing_capability.formats, *capability.formats}
                            )
                            existing_capability.styles = sorted(
                                {*existing_capability.styles, *capability.styles}
                            )
                            if capability.time_domain is not None:
                                existing_capability.time_domain = capability.time_domain
                            existing_capability.nearest_value = (
                                existing_capability.nearest_value or capability.nearest_value
                            )
        self.capabilities_cache.set(cache_key, aggregated)
        return aggregated

    def describe_domains(
        self,
        projection: str,
        flavor: str,
        layer_id: str,
        matrix_set: str,
    ) -> GIBSTimeDomain:
        cache_key = f"domain:{projection}:{flavor}:{layer_id}:{matrix_set}"
        cached = self.domain_cache.get(cache_key)
        if cached:
            return cached
        root = self._service_root("wmts", projection, flavor)
        params = {
            "SERVICE": "WMTS",
            "REQUEST": "DescribeDomains",
            "Layer": layer_id,
            "TileMatrixSet": matrix_set,
        }
        url = f"{root}{self.WMTS_KVP}?{urlencode(params)}"
        xml_text = self._http_get(url)
        tree = ElementTree.fromstring(xml_text)
        dimension = tree.find(".//DimensionDomain")
        values: list[str] = []
        default_value = None
        if dimension is not None:
            default_value = dimension.findtext("DefaultValue")
            value_texts = [node.text for node in dimension.findall("Value") if node.text]
            values = expand_time_values(value_texts)
        domain = GIBSTimeDomain(default=default_value, values=values, current=False, limited=False)
        self.domain_cache.set(cache_key, domain)
        return domain


###############################################################################
class ImageryCache:
    def __init__(self, settings: GIBSSettings) -> None:
        self.settings = settings
        self.cache = TTLCache(settings.imagery_ttl, settings.imagery_cache_size)

    def key(self, request: GIBSRequest) -> str:
        if request.service == "wmts":
            return (
                f"wmts:{request.layer}:{request.time}:{request.tile_matrix_set}:"
                f"{request.tile_matrix}:{request.tile_row}:{request.tile_col}:{request.mime_type}"
            )
        bbox_values = request.bbox.as_list() if request.bbox else []
        return (
            f"wms:{request.layer}:{request.time}:{request.wms_version}:{request.projection}:"
            f"{','.join(bbox_values)}:{request.width}:{request.height}:{request.mime_type}"
        )

    def get(self, request: GIBSRequest) -> bytes | None:
        cached = self.cache.get(self.key(request))
        if cached is None:
            return None
        return cached

    def set(self, request: GIBSRequest, content: bytes, headers: dict[str, str]) -> None:
        ttl_override = None
        cache_control = headers.get("cache-control")
        if cache_control and "max-age" in cache_control:
            try:
                max_age = next(
                    int(part.split("=")[1])
                    for part in cache_control.split(",")
                    if part.strip().startswith("max-age")
                )
                ttl_override = float(max_age)
            except (ValueError, StopIteration):
                ttl_override = None
        self.cache.set(self.key(request), content, ttl_override)


###############################################################################
class EndpointBuilder:
    def __init__(self, settings: GIBSSettings) -> None:
        self.settings = settings

    def wmts(self, projection: str, flavor: str) -> str:
        projection = normalize_projection(projection)
        flavor = normalize_flavor(flavor)
        return f"https://gibs.earthdata.nasa.gov/wmts/{projection}/{flavor}"

    def wms(self, projection: str, flavor: str) -> str:
        projection = normalize_projection(projection)
        flavor = normalize_flavor(flavor)
        return f"https://gibs.earthdata.nasa.gov/wms/{projection}/{flavor}"

    def shard_endpoint(self, base_url: str, attempt: int) -> str:
        if not self.settings.enable_domain_sharding:
            return base_url
        shards = self.settings.shard_domains
        if not shards:
            return base_url
        domain_index = attempt % len(shards)
        shard_domain = shards[domain_index]
        if shard_domain in base_url:
            return base_url
        return base_url.replace("gibs.earthdata.nasa.gov", shard_domain)


###############################################################################
class GIBSClient:
    def __init__(self, settings: GIBSSettings | None = None) -> None:
        self.settings = settings or GIBSSettings.from_environment()
        self.discovery = GIBSDiscovery(self.settings)
        self.imagery_cache = ImageryCache(self.settings)
        self.transformers = ProjectionTransformers()
        self.endpoint_builder = EndpointBuilder(self.settings)
        self.layer_presets = {
            "natural color": "MODIS_Terra_CorrectedReflectance_TrueColor",
            "topographic": "BlueMarble_ShadedRelief_Bathymetry",
            "population density": "GPW_Population_Density_2020",
            "weather overlay": "MODIS_Terra_CloudTopPressure_Day",
        }
        self.city_presets = {
            "rome": (41.9028, 12.4964),
            "milan": (45.4642, 9.19),
            "naples": (40.8518, 14.2681),
            "new york": (40.7128, -74.006),
            "los angeles": (34.0522, -118.2437),
            "chicago": (41.8781, -87.6298),
            "london": (51.5074, -0.1278),
            "manchester": (53.4808, -2.2426),
            "toronto": (43.6532, -79.3832),
            "vancouver": (49.2827, -123.1207),
            "sydney": (-33.8688, 151.2093),
            "melbourne": (-37.8136, 144.9631),
            "brisbane": (-27.4698, 153.0251),
            "ottawa": (45.4215, -75.6972),
            "montreal": (45.5017, -73.5673),
        }
        self.country_presets = {
            "italy": (41.8719, 12.5674),
            "united states": (39.8283, -98.5795),
            "united kingdom": (55.3781, -3.4360),
            "canada": (56.1304, -106.3468),
            "australia": (-25.2744, 133.7751),
        }

    def build_imagery_payload(self, request: MapRequest) -> GIBSImageryPayload:
        map_options = request.map_options
        location = self.resolve_location(request)
        projection = normalize_projection(map_options.projection or self.settings.projection_default)
        flavor = normalize_flavor(map_options.endpoint_flavor or self.settings.endpoint_flavor_default)
        layer_id = self.resolve_layer_identifier(map_options.layer_id, request.filter)
        if not layer_id:
            raise ValueError("Unable to determine a NASA GIBS layer identifier.")
        if map_options.service == "wmts":
            payload = self._build_wmts_payload(
                layer_id=layer_id,
                projection=projection,
                flavor=flavor,
                location=location,
                map_options=map_options,
                temporal=request.temporal,
            )
        else:
            payload = self._build_wms_payload(
                layer_id=layer_id,
                projection=projection,
                flavor=flavor,
                location=location,
                map_options=map_options,
                temporal=request.temporal,
            )
        return payload

    def resolve_layer_identifier(self, explicit_layer: str | None, filter_name: str | None) -> str | None:
        if explicit_layer:
            return explicit_layer
        if not filter_name:
            return self.layer_presets.get("natural color")
        normalized = filter_name.strip().lower()
        return self.layer_presets.get(normalized, self.layer_presets.get("natural color"))

    def resolve_location(self, request: MapRequest) -> ResolvedLocation:
        if request.mode == "coordinates" and request.coordinates is not None:
            coordinates = request.coordinates
            return ResolvedLocation(
                latitude=coordinates.latitude,
                longitude=coordinates.longitude,
                source="coordinates",
                reference="Coordinates provided by user",
            )
        if request.location is not None:
            location = request.location
            if location.city:
                city_key = location.city.strip().lower()
                if city_key in self.city_presets:
                    latitude, longitude = self.city_presets[city_key]
                    return ResolvedLocation(
                        latitude=latitude,
                        longitude=longitude,
                        source="city",
                        reference=location.city,
                    )
            if location.country:
                country_key = location.country.strip().lower()
                if country_key in self.country_presets:
                    latitude, longitude = self.country_presets[country_key]
                    return ResolvedLocation(
                        latitude=latitude,
                        longitude=longitude,
                        source="country",
                        reference=location.country,
                    )
        raise ValueError("Unable to resolve location. Provide coordinates or choose a supported location.")

    def _build_wmts_payload(
        self,
        layer_id: str,
        projection: str,
        flavor: str,
        location: ResolvedLocation,
        map_options: GIBSMapOptions,
        temporal: TemporalContext,
    ) -> GIBSImageryPayload:
        layers, matrix_sets = self.discovery.fetch_wmts(projection, flavor)
        layer = layers.get(layer_id)
        if layer is None:
            raise ValueError(f"Layer {layer_id} is not available for WMTS in projection {projection}.")
        projection_caps = layer.projections.get(projection)
        if projection_caps is None or projection_caps.wmts is None:
            raise ValueError(f"Layer {layer_id} does not support WMTS in projection {projection}.")
        wmts_caps = projection_caps.wmts
        matrix_set_id = self._resolve_matrix_set(map_options.wmts, wmts_caps)
        matrix_set = matrix_sets.get(matrix_set_id)
        if matrix_set is None:
            raise ValueError(f"TileMatrixSet {matrix_set_id} not available in WMTS capabilities.")
        time_domain = wmts_caps.time_domains.get(matrix_set_id)
        if time_domain is not None and time_domain.limited:
            time_domain = self.discovery.describe_domains(projection, flavor, layer_id, matrix_set_id)
        temporal_parameters = TemporalParameters(
            reference_date=temporal.reference_date,
            time_of_day=temporal.time_of_day,
            fallback_year=temporal.timeline_year,
        )
        explicit_time = map_options.time_value or temporal_parameters.iso_value()
        resolver = GIBSTimeResolver(self.settings)
        time_selection = resolver.resolve(explicit_time, time_domain, temporal_parameters.iso_value())
        fallback = resolver.fallback_today(time_domain)
        if fallback and fallback.snapped:
            time_selection = fallback
        tile_matrix_identifier = self._resolve_tile_matrix(map_options.wmts, matrix_set)
        calculator = self._build_tile_calculator(matrix_set, projection)
        tile_coordinates = calculator.compute_tile(
            latitude=location.latitude,
            longitude=location.longitude,
            tile_matrix=tile_matrix_identifier,
        )
        style = map_options.style or (wmts_caps.styles[0] if wmts_caps.styles else "default")
        mime_type = map_options.format or (wmts_caps.formats[0] if wmts_caps.formats else "image/jpeg")
        image_format = mime_type.split("/")[-1]
        endpoint = self.endpoint_builder.wmts(projection, flavor)
        kvp_endpoint = f"{endpoint}/{self.discovery.WMTS_KVP}"
        request_payload = GIBSRequest(
            service="wmts",
            projection=projection,
            endpoint=endpoint,
            kvp_endpoint=kvp_endpoint,
            layer=layer_id,
            style=style,
            time=time_selection.iso_value,
            tile_matrix_set=matrix_set.identifier,
            tile_matrix=tile_coordinates.tile_matrix,
            tile_row=tile_coordinates.row,
            tile_col=tile_coordinates.column,
            image_format=image_format,
            mime_type=mime_type,
        )
        kvp_url = f"{kvp_endpoint}?{urlencode(request_payload.kvp_parameters)}"
        caption = self._compose_caption(location, map_options, time_selection.iso_value, tile_coordinates)
        debug = {
            "layer": layer_id,
            "projection": projection,
            "matrix_set": matrix_set.identifier,
            "tile_matrix": tile_coordinates.tile_matrix,
            "time": time_selection.iso_value,
            "snapped": time_selection.snapped,
            "reason": time_selection.reason,
            "flavor": flavor,
            "service": "wmts",
        }
        message = "NASA GIBS WMTS imagery request generated successfully."
        return GIBSImageryPayload(
            request=request_payload,
            layer=layer,
            projection=projection,
            tile=tile_coordinates,
            bbox=None,
            location=location,
            caption=caption,
            message=message,
            image_url=request_payload.restful_url,
            kvp_url=kvp_url,
            debug=debug,
        )

    def _build_wms_payload(
        self,
        layer_id: str,
        projection: str,
        flavor: str,
        location: ResolvedLocation,
        map_options: GIBSMapOptions,
        temporal: TemporalContext,
    ) -> GIBSImageryPayload:
        layers = self.discovery.fetch_wms(projection, flavor)
        layer = layers.get(layer_id)
        if layer is None:
            raise ValueError(f"Layer {layer_id} is not available for WMS in projection {projection}.")
        projection_caps = layer.projections.get(projection)
        if projection_caps is None or not projection_caps.wms:
            raise ValueError(f"Layer {layer_id} does not support WMS in projection {projection}.")
        version = map_options.wms.version if map_options.wms else "1.1.1"
        if version not in projection_caps.wms:
            version = next(iter(projection_caps.wms.keys()))
        wms_caps = projection_caps.wms[version]
        options = map_options.wms or WMSRequestOptions()
        time_domain = wms_caps.time_domain
        temporal_parameters = TemporalParameters(
            reference_date=temporal.reference_date,
            time_of_day=temporal.time_of_day,
            fallback_year=temporal.timeline_year,
        )
        explicit_time = map_options.time_value or temporal_parameters.iso_value()
        resolver = GIBSTimeResolver(self.settings)
        time_selection = resolver.resolve(explicit_time, time_domain, temporal_parameters.iso_value())
        fallback = resolver.fallback_today(time_domain)
        if fallback and fallback.snapped:
            time_selection = fallback
        bbox = self._build_wms_bbox(location, projection, options)
        style = options.style or (wms_caps.styles[0] if wms_caps.styles else "default")
        mime_type = options.format or (wms_caps.formats[0] if wms_caps.formats else "image/png")
        endpoint = self.endpoint_builder.wms(projection, flavor)
        kvp_endpoint = f"{endpoint}/{self.discovery.WMS_KVP}"
        axis_order = "latlon" if version == "1.3.0" and projection == "epsg4326" else "lonlat"
        request_payload = GIBSRequest(
            service="wms",
            projection=projection,
            endpoint=endpoint,
            kvp_endpoint=kvp_endpoint,
            layer=layer_id,
            style=style,
            time=time_selection.iso_value,
            tile_matrix_set=None,
            tile_matrix=None,
            tile_row=None,
            tile_col=None,
            image_format=mime_type.split("/")[-1],
            mime_type=mime_type,
            width=options.width,
            height=options.height,
            bbox=bbox,
            wms_version=version,
            axis_order=axis_order,
            nearest_value=wms_caps.nearest_value,
        )
        kvp_url = f"{kvp_endpoint}?{urlencode(request_payload.kvp_parameters)}"
        caption = self._compose_wms_caption(location, map_options, time_selection.iso_value, bbox)
        message = "NASA GIBS WMS imagery request generated successfully."
        debug = {
            "layer": layer_id,
            "projection": projection,
            "bbox": bbox.as_list(),
            "time": time_selection.iso_value,
            "snapped": time_selection.snapped,
            "reason": time_selection.reason,
            "flavor": flavor,
            "service": "wms",
            "version": version,
        }
        return GIBSImageryPayload(
            request=request_payload,
            layer=layer,
            projection=projection,
            tile=None,
            bbox=bbox,
            location=location,
            caption=caption,
            message=message,
            image_url=request_payload.restful_url,
            kvp_url=kvp_url,
            debug=debug,
        )

    def _resolve_matrix_set(
        self, options: WMTSRequestOptions | None, wmts_caps: WMTSProjectionCapabilities
    ) -> str:
        if options and options.tile_matrix_set:
            if options.tile_matrix_set not in wmts_caps.matrix_sets:
                raise ValueError(
                    f"Tile matrix set {options.tile_matrix_set} is not supported for the selected layer."
                )
            return options.tile_matrix_set
        if not wmts_caps.matrix_sets:
            raise ValueError("WMTS layer does not advertise any tile matrix sets.")
        return wmts_caps.matrix_sets[0]

    def _resolve_tile_matrix(
        self,
        options: WMTSRequestOptions | None,
        matrix_set: GIBSMatrixSet,
    ) -> str:
        if options and options.tile_matrix:
            if options.tile_matrix not in matrix_set.levels:
                raise ValueError(
                    f"Tile matrix {options.tile_matrix} is not available in matrix set {matrix_set.identifier}."
                )
            return options.tile_matrix
        if options and options.zoom is not None:
            zoom = options.zoom
            if zoom < 0 or zoom >= len(matrix_set.levels):
                raise ValueError(
                    f"Zoom level {zoom} is outside the valid range for matrix set {matrix_set.identifier}."
                )
            return matrix_set.levels[zoom]
        return matrix_set.levels[-1]

    def _build_tile_calculator(
        self, matrix_set: GIBSMatrixSet, projection: str
    ) -> WMTSMatrixCalculator:
        if projection == "epsg3857":
            return WMTS3857Calculator(matrix_set, projection, self.transformers)
        return WMTSMatrixCalculator(matrix_set, projection, self.transformers)

    def _build_wms_bbox(
        self, location: ResolvedLocation, projection: str, options: WMSRequestOptions
    ) -> WMSBoundingBox:
        if options.size_km is not None:
            half_width = options.size_km
            half_height = options.size_km
        else:
            half_width = options.width_km or 50.0
            half_height = options.height_km or 50.0
        delta_lat = half_height / 110.6
        lat_radians = math.radians(location.latitude)
        cos_lat = max(math.cos(lat_radians), 1e-6)
        delta_lon = half_width / (111.32 * cos_lat)
        min_lat = max(location.latitude - delta_lat, -90.0)
        max_lat = min(location.latitude + delta_lat, 90.0)
        min_lon = ((location.longitude - delta_lon + 180.0) % 360.0) - 180.0
        max_lon = ((location.longitude + delta_lon + 180.0) % 360.0) - 180.0
        axis_order = "latlon" if options.version == "1.3.0" and projection == "epsg4326" else "lonlat"
        return WMSBoundingBox(minx=min_lon, miny=min_lat, maxx=max_lon, maxy=max_lat, axis_order=axis_order)

    def _compose_caption(
        self,
        location: ResolvedLocation,
        map_options: GIBSMapOptions,
        time_iso: str,
        tile: GIBSTileCoordinates,
    ) -> str:
        parts: list[str] = [f"Layer: {map_options.layer_id or 'auto'}", f"Time: {time_iso}"]
        if location.reference:
            parts.append(f"Location: {location.reference}")
        else:
            parts.append(f"Coordinates: ({location.latitude:.4f}, {location.longitude:.4f})")
        parts.append(f"Tile: {tile.tile_matrix_set}/{tile.tile_matrix}/{tile.column}/{tile.row}")
        parts.append(f"Projection: {map_options.projection}")
        parts.append(f"Service: WMTS")
        return " | ".join(parts)

    def _compose_wms_caption(
        self,
        location: ResolvedLocation,
        map_options: GIBSMapOptions,
        time_iso: str,
        bbox: WMSBoundingBox,
    ) -> str:
        parts: list[str] = [f"Layer: {map_options.layer_id or 'auto'}", f"Time: {time_iso}"]
        if location.reference:
            parts.append(f"Location: {location.reference}")
        else:
            parts.append(f"Coordinates: ({location.latitude:.4f}, {location.longitude:.4f})")
        parts.append("BBOX: " + ", ".join(bbox.as_list()))
        parts.append(f"Projection: {map_options.projection}")
        parts.append(f"Service: WMS {map_options.wms.version if map_options.wms else '1.1.1'}")
        return " | ".join(parts)

    async def download_imagery(self, request: GIBSRequest) -> bytes:
        cached = self.imagery_cache.get(request)
        if cached is not None:
            return cached
        headers = {"Accept": request.mime_type, "User-Agent": self.settings.user_agent}
        attempts: list[tuple[str, dict[str, str] | None]] = []
        if request.service == "wmts":
            attempts.append((request.restful_url, None))
            attempts.append((request.kvp_endpoint, request.kvp_parameters))
        else:
            attempts.append((request.restful_url, None))
            attempts.append((request.kvp_endpoint, request.kvp_parameters))
        async with httpx.AsyncClient(timeout=self.settings.imagery_timeout, headers=headers) as client:
            for index, (endpoint, params) in enumerate(attempts):
                url = endpoint
                if request.service == "wmts" and params is None and index > 0:
                    url = self.endpoint_builder.shard_endpoint(endpoint, index)
                try:
                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    content = response.content
                    self.imagery_cache.set(request, content, response.headers)
                    return content
                except httpx.HTTPStatusError as exc:
                    if request.service == "wmts" and params is None:
                        continue
                    detail = exc.response.text.strip() or f"HTTP {exc.response.status_code}"
                    raise ValueError(detail) from exc
                except httpx.RequestError as exc:
                    if request.service == "wmts" and params is None:
                        continue
                    raise ValueError(f"Unable to reach NASA GIBS service: {exc}") from exc
        raise ValueError("Unable to retrieve imagery from NASA GIBS service.")

