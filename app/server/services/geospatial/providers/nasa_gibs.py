from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from xml.etree import ElementTree

from server.common.constants import NASA_ATTRIBUTION
from server.domain.geographics import (
    GeospatialLayerRenderDescriptor,
    GeospatialProviderLayerDescriptor,
)
from server.services.geospatial.cache import CacheLookupStatus, GeospatialCache
from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderRequest,
    ProviderResponse,
    ProviderUnavailableError,
)
from server.services.geospatial.providers.http import (
    TextFetcher,
    call_text_fetcher,
    fetch_text_url,
)

GIBS_WMTS_CAPABILITIES_URL = (
    "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/WMTSCapabilities.xml"
)
GIBS_WMS_CAPABILITIES_URL = (
    "https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi?"
    "service=WMS&request=GetCapabilities&version=1.3.0"
)
GIBS_WMTS_REST_BASE_URL = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best"
GIBS_WMS_BASE_URL = "https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi"
GIBS_USER_AGENT = {"User-Agent": "AEGIS/1.0"}


###############################################################################
@dataclass
class ParsedGIBSLayer:
    layer_id: str
    title: str
    abstract: str | None = None
    protocols: set[str] = field(default_factory=set)
    crs: set[str] = field(default_factory=set)
    formats: set[str] = field(default_factory=set)
    styles: set[str] = field(default_factory=set)
    time_extent: str | None = None
    default_time: str | None = None
    tile_matrix_sets: set[str] = field(default_factory=set)


###############################################################################
class NASAGIBSProvider(GeospatialProvider):
    provider_id = "gibs"

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        fetcher: TextFetcher | None = None,
        cache: GeospatialCache | None = None,
        cache_ttl_seconds: int = 3600,
        stale_while_revalidate_seconds: int = 86400,
    ) -> None:
        self.fetcher = fetcher or fetch_text_url
        self.cache = cache or GeospatialCache()
        self.cache_ttl_seconds = cache_ttl_seconds
        self.stale_while_revalidate_seconds = stale_while_revalidate_seconds

    # -------------------------------------------------------------------------
    async def list_layers(
        self,
        *,
        query: str | None = None,
        limit: int = 100,
        refresh: bool = False,
    ) -> list[GeospatialProviderLayerDescriptor]:
        wmts = self._parse_wmts_layers(await self._load_wmts_capabilities(refresh=refresh))
        wms = self._parse_wms_layers(await self._load_wms_capabilities(refresh=refresh))
        layers = self._merge_layer_descriptors(wmts, wms)
        query_text = str(query or "").strip().casefold()
        if query_text:
            layers = [
                layer
                for layer in layers
                if query_text in f"{layer.layer_id} {layer.title} {layer.abstract or ''}".casefold()
            ]
        return layers[: max(1, min(int(limit), 250))]

    # -------------------------------------------------------------------------
    async def describe_layer(
        self,
        layer_id: str,
        *,
        refresh: bool = False,
    ) -> GeospatialProviderLayerDescriptor:
        normalized = str(layer_id).strip()
        for layer in await self.list_layers(limit=250, refresh=refresh):
            if layer.layer_id == normalized:
                return layer
        raise ProviderUnavailableError(f"NASA GIBS layer '{layer_id}' was not found.")

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        layer_id = str(request.params.get("layer_id") or request.params.get("layer") or request.capability_id)
        layer = await self.describe_layer(layer_id)
        render = layer.render
        if render is not None and request.time is not None:
            render = render.model_copy(update={"time": request.time.date().isoformat()})
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "layer": layer.model_dump(mode="json"),
                "render": render.model_dump(mode="json") if render else None,
            },
            attribution=[NASA_ATTRIBUTION],
            warnings=list(layer.warnings),
        )

    # -------------------------------------------------------------------------
    async def _load_wmts_capabilities(self, *, refresh: bool) -> ElementTree.Element:
        return await self._load_xml("wmts", GIBS_WMTS_CAPABILITIES_URL, refresh=refresh)

    # -------------------------------------------------------------------------
    async def _load_wms_capabilities(self, *, refresh: bool) -> ElementTree.Element:
        return await self._load_xml("wms", GIBS_WMS_CAPABILITIES_URL, refresh=refresh)

    # -------------------------------------------------------------------------
    async def _load_xml(self, cache_key: str, url: str, *, refresh: bool) -> ElementTree.Element:
        full_cache_key = f"{self.provider_id}:capabilities:{cache_key}"
        cached = self.cache.get(full_cache_key)
        if not refresh and cached.status in {CacheLookupStatus.HIT, CacheLookupStatus.STALE} and isinstance(cached.value, str):
            return ElementTree.fromstring(cached.value)
        try:
            xml_text = await call_text_fetcher(self.fetcher, url, GIBS_USER_AGENT)
        except Exception as exc:
            if cached.status == CacheLookupStatus.STALE and isinstance(cached.value, str):
                return ElementTree.fromstring(cached.value)
            if isinstance(exc, ProviderUnavailableError):
                raise
            raise ProviderUnavailableError("NASA GIBS capabilities could not be fetched.") from exc
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError as exc:
            raise ProviderUnavailableError("NASA GIBS capabilities returned malformed XML.") from exc
        self.cache.set(
            full_cache_key,
            xml_text,
            ttl_seconds=self.cache_ttl_seconds,
            stale_while_revalidate_seconds=self.stale_while_revalidate_seconds,
        )
        return root

    # -------------------------------------------------------------------------
    def _parse_wmts_layers(self, root: ElementTree.Element) -> dict[str, ParsedGIBSLayer]:
        layers: dict[str, ParsedGIBSLayer] = {}
        for element in root.findall(".//{*}Contents/{*}Layer"):
            layer_id = self._child_text(element, "Identifier")
            if not layer_id:
                continue
            layer = ParsedGIBSLayer(
                layer_id=layer_id,
                title=self._child_text(element, "Title") or layer_id,
                abstract=self._child_text(element, "Abstract"),
                protocols={"wmts"},
                crs={"EPSG:3857"},
            )
            for fmt in element.findall("{*}Format"):
                if fmt.text and fmt.text.strip():
                    layer.formats.add(fmt.text.strip())
            for style in element.findall("{*}Style"):
                identifier = self._child_text(style, "Identifier")
                if identifier:
                    layer.styles.add(identifier)
            for matrix in element.findall("{*}TileMatrixSetLink/{*}TileMatrixSet"):
                if matrix.text and matrix.text.strip():
                    layer.tile_matrix_sets.add(matrix.text.strip())
            for dimension in element.findall("{*}Dimension"):
                identifier = self._child_text(dimension, "Identifier")
                if identifier and identifier.lower() == "time":
                    default = self._child_text(dimension, "Default")
                    values = [
                        value.text.strip()
                        for value in dimension.findall("{*}Value")
                        if value.text and value.text.strip()
                    ]
                    layer.default_time = default or self._default_time_from_values(values)
                    layer.time_extent = ",".join(values) if values else None
            layers[layer_id] = layer
        return layers

    # -------------------------------------------------------------------------
    def _parse_wms_layers(self, root: ElementTree.Element) -> dict[str, ParsedGIBSLayer]:
        layers: dict[str, ParsedGIBSLayer] = {}
        request = root.find(".//{*}Request/{*}GetMap")
        get_map_formats = [
            fmt.text.strip()
            for fmt in (request.findall("{*}Format") if request is not None else [])
            if fmt.text and fmt.text.strip()
        ]
        for element in root.findall(".//{*}Layer"):
            layer_id = self._child_text(element, "Name")
            if not layer_id:
                continue
            layer = ParsedGIBSLayer(
                layer_id=layer_id,
                title=self._child_text(element, "Title") or layer_id,
                abstract=self._child_text(element, "Abstract"),
                protocols={"wms"},
            )
            layer.formats.update(get_map_formats)
            for crs in [*element.findall("{*}CRS"), *element.findall("{*}SRS")]:
                if crs.text and crs.text.strip():
                    layer.crs.add(crs.text.strip())
            for style in element.findall("{*}Style"):
                style_name = self._child_text(style, "Name")
                if style_name:
                    layer.styles.add(style_name)
            for dimension in element.findall("{*}Dimension"):
                if str(dimension.attrib.get("name") or "").lower() == "time":
                    value = str(dimension.text or "").strip()
                    layer.time_extent = value or None
                    layer.default_time = str(dimension.attrib.get("default") or "").strip() or self._default_time_from_extent(value)
            layers[layer_id] = layer
        return layers

    # -------------------------------------------------------------------------
    def _merge_layer_descriptors(
        self,
        wmts_layers: dict[str, ParsedGIBSLayer],
        wms_layers: dict[str, ParsedGIBSLayer],
    ) -> list[GeospatialProviderLayerDescriptor]:
        descriptors: list[GeospatialProviderLayerDescriptor] = []
        for layer_id in sorted({*wmts_layers, *wms_layers}):
            parsed = wmts_layers.get(layer_id) or wms_layers[layer_id]
            if layer_id in wmts_layers and layer_id in wms_layers:
                parsed = self._merge_parsed_layers(wmts_layers[layer_id], wms_layers[layer_id])
            render = self._build_render_descriptor(parsed)
            descriptors.append(
                GeospatialProviderLayerDescriptor(
                    provider=self.provider_id,
                    layer_id=parsed.layer_id,
                    title=parsed.title,
                    abstract=parsed.abstract,
                    rendering_mode=render.rendering_mode if render else "metadata-only",
                    source_protocol=render.source_protocol if render else "provider-api",
                    data_format=next(iter(sorted(parsed.formats)), "image/png"),
                    geometry_type="raster-grid",
                    queryable=False,
                    crs=sorted(parsed.crs),
                    formats=sorted(parsed.formats),
                    styles=sorted(parsed.styles) or ["default"],
                    time_extent=parsed.time_extent,
                    default_time=parsed.default_time,
                    tile_matrix_sets=sorted(parsed.tile_matrix_sets),
                    render=render,
                    attribution=[NASA_ATTRIBUTION],
                    warnings=[] if render else ["Layer capabilities do not include renderable WMS or WMTS metadata."],
                )
            )
        return descriptors

    # -------------------------------------------------------------------------
    def _build_render_descriptor(
        self,
        layer: ParsedGIBSLayer,
        *,
        preferred_mode: Literal["wmts", "wms"] = "wmts",
    ) -> GeospatialLayerRenderDescriptor | None:
        formats = sorted(layer.formats)
        image_format = "image/png" if "image/png" in formats else next(iter(formats), "image/png")
        style = "default" if "default" in layer.styles else next(iter(sorted(layer.styles)), "default")
        matrix_sets = sorted(layer.tile_matrix_sets)
        matrix_set = next((item for item in matrix_sets if "GoogleMapsCompatible" in item), None) or next(iter(matrix_sets), None)
        if preferred_mode == "wmts" and "wmts" in layer.protocols and matrix_set:
            return GeospatialLayerRenderDescriptor(
                provider=self.provider_id,
                layer_id=layer.layer_id,
                rendering_mode="wmts",
                source_protocol="wmts",
                url=GIBS_WMTS_REST_BASE_URL,
                tile_url_template=(
                    f"{GIBS_WMTS_REST_BASE_URL}/{layer.layer_id}/{style}/"
                    f"{layer.default_time or '{time}'}/{matrix_set}/{{z}}/{{y}}/{{x}}"
                    f".{self._extension_for_format(image_format)}"
                ),
                crs="EPSG:3857",
                format=image_format,
                style=style,
                default_time=layer.default_time,
                tile_matrix_set=matrix_set,
                tile_size=256,
                min_zoom=0,
                max_zoom=9,
                attribution=[NASA_ATTRIBUTION],
            )
        if "wms" in layer.protocols:
            crs = "EPSG:3857" if "EPSG:3857" in layer.crs else next(iter(sorted(layer.crs)), "EPSG:3857")
            return GeospatialLayerRenderDescriptor(
                provider=self.provider_id,
                layer_id=layer.layer_id,
                rendering_mode="wms",
                source_protocol="wms",
                url=GIBS_WMS_BASE_URL,
                crs=crs,
                format=image_format,
                style=style,
                default_time=layer.default_time,
                tile_size=256,
                attribution=[NASA_ATTRIBUTION],
            )
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def _merge_parsed_layers(primary: ParsedGIBSLayer, secondary: ParsedGIBSLayer) -> ParsedGIBSLayer:
        return ParsedGIBSLayer(
            layer_id=primary.layer_id,
            title=primary.title or secondary.title,
            abstract=primary.abstract or secondary.abstract,
            protocols={*primary.protocols, *secondary.protocols},
            crs={*primary.crs, *secondary.crs},
            formats={*primary.formats, *secondary.formats},
            styles={*primary.styles, *secondary.styles},
            time_extent=primary.time_extent or secondary.time_extent,
            default_time=primary.default_time or secondary.default_time,
            tile_matrix_sets={*primary.tile_matrix_sets, *secondary.tile_matrix_sets},
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _child_text(element: ElementTree.Element, local_name: str) -> str | None:
        child = element.find(f"{{*}}{local_name}")
        if child is None or child.text is None:
            return None
        stripped = child.text.strip()
        return stripped or None

    # -------------------------------------------------------------------------
    @staticmethod
    def _default_time_from_values(values: list[str]) -> str | None:
        if not values:
            return None
        return values[-1].split("/")[-1].split(",")[-1].strip() or None

    # -------------------------------------------------------------------------
    @classmethod
    def _default_time_from_extent(cls, value: str | None) -> str | None:
        if not value:
            return None
        return cls._default_time_from_values([part.strip() for part in value.split(",") if part.strip()])

    # -------------------------------------------------------------------------
    @staticmethod
    def _extension_for_format(image_format: str) -> str:
        return {
            "image/png": "png",
            "image/jpeg": "jpg",
            "image/jpg": "jpg",
        }.get(image_format.lower(), "png")
