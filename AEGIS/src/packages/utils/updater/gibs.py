from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from AEGIS.src.packages.logger import logger
from AEGIS.src.packages.utils.repository.serializer import DataSerializer


GIBS_CAPABILITIES_ENDPOINTS = {
    "EPSG:4326": "https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/1.0.0/WMTSCapabilities.xml",
    "EPSG:3857": "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/WMTSCapabilities.xml",
    "EPSG:3413": "https://gibs.earthdata.nasa.gov/wmts/epsg3413/best/1.0.0/WMTSCapabilities.xml",
    "EPSG:3031": "https://gibs.earthdata.nasa.gov/wmts/epsg3031/best/1.0.0/WMTSCapabilities.xml",
}
OWS_NAMESPACES = {"ows": "http://www.opengis.net/ows/1.1"}
USER_AGENT = "AEGIS-GIBS-LayerSync/1.0"
REQUEST_TIMEOUT = 30

type LayerPayload = dict[str, str | None]


###############################################################################
class LayerHarvestError(RuntimeError):
    pass


###############################################################################
@dataclass
class LayerAggregate:
    layer_id: str
    title: str
    abstract: str | None
    projections: set[str]
    source_urls: set[str]


###############################################################################
class GIBSLayersUpdater:
    def __init__(
        self,
        serializer: DataSerializer | None = None,
        endpoints: dict[str, str] | None = None,
    ) -> None:
        self.serializer = serializer or DataSerializer()
        self.endpoints = endpoints or GIBS_CAPABILITIES_ENDPOINTS

    # -------------------------------------------------------------------------
    def update(self) -> None:
        layers = self.collect_layers()
        self.serializer.upsert_gibs_layers(layers)
        logger.info("Stored %s unique GIBS layers", len(layers))

    # -------------------------------------------------------------------------
    def collect_layers(self) -> list[LayerPayload]:
        aggregated: dict[str, LayerAggregate] = {}
        for projection, url in self.endpoints.items():
            payload = self.fetch_capabilities(url)
            for layer in self.parse_layers(payload):
                layer_id = layer["layer_id"]
                if not layer_id:
                    continue
                entry = aggregated.get(layer_id)
                if not entry:
                    entry = LayerAggregate(
                        layer_id=layer_id,
                        title=layer["title"] or layer_id,
                        abstract=layer["abstract"],
                        projections=set(),
                        source_urls=set(),
                    )
                    aggregated[layer_id] = entry
                if layer["title"] and entry.title == entry.layer_id:
                    entry.title = layer["title"]
                if layer["abstract"]:
                    entry.abstract = layer["abstract"]
                entry.projections.add(projection)
                entry.source_urls.add(url)

        normalized: list[LayerPayload] = []
        for snapshot in aggregated.values():
            normalized.append(
                {
                    "layer_id": snapshot.layer_id,
                    "title": snapshot.title,
                    "abstract": snapshot.abstract,
                    "projections": json.dumps(sorted(snapshot.projections)),
                    "source_urls": json.dumps(sorted(snapshot.source_urls)),
                }
            )
        return normalized

    # -------------------------------------------------------------------------
    def fetch_capabilities(self, url: str) -> bytes:
        request = Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                return response.read()
        except (HTTPError, URLError) as exc:  # pragma: no cover - network failures
            raise LayerHarvestError(f"Failed to download capabilities at {url}") from exc

    # -------------------------------------------------------------------------
    def parse_layers(self, payload: bytes) -> list[LayerPayload]:
        try:
            root = ElementTree.fromstring(payload)
        except ElementTree.ParseError as exc:  # pragma: no cover - invalid XML
            raise LayerHarvestError("Unable to parse capabilities payload.") from exc

        layers: list[LayerPayload] = []
        for layer in root.findall(".//{*}Layer"):
            identifier = layer.findtext("ows:Identifier", namespaces=OWS_NAMESPACES)
            if not identifier:
                continue
            title = layer.findtext("ows:Title", namespaces=OWS_NAMESPACES)
            abstract = layer.findtext("ows:Abstract", namespaces=OWS_NAMESPACES)
            layers.append(
                {
                    "layer_id": identifier.strip(),
                    "title": (title or identifier).strip(),
                    "abstract": abstract.strip() if abstract else None,
                }
            )
        return layers
