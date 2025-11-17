from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from tqdm import tqdm

from AEGIS.src.packages.configurations import configurations
from AEGIS.src.packages.logger import logger
from AEGIS.src.packages.utils.repository.serializer import DataSerializer


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
        user_agent: str | None = None,
        ows_namespaces: dict[str, str] | None = None,
        request_timeout: float | None = None,
    ) -> None:
        self.serializer = serializer or DataSerializer()
        settings = configurations.gibs
        self.endpoints = copy.deepcopy(
            endpoints or settings.capabilities_endpoints
        )
        self.ows_namespaces = copy.deepcopy(
            ows_namespaces or settings.ows_namespaces
        )
        self.user_agent = user_agent or settings.layer_sync_user_agent
        self.request_timeout = request_timeout or settings.layer_sync_timeout

    # -------------------------------------------------------------------------
    def update(self) -> None:
        layers = self.collect_layers()
        self.serializer.upsert_gibs_layers(layers)
        logger.info("Stored %s unique GIBS layers", len(layers))

    # -------------------------------------------------------------------------
    def collect_layers(self) -> list[LayerPayload]:
        aggregated: dict[str, LayerAggregate] = {}
        for projection, url in tqdm(self.endpoints.items()):
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
        request = Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urlopen(request, timeout=self.request_timeout) as response:
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
            identifier = layer.findtext(
                "ows:Identifier", namespaces=self.ows_namespaces
            )
            if not identifier:
                continue
            title = layer.findtext("ows:Title", namespaces=self.ows_namespaces)
            abstract = layer.findtext("ows:Abstract", namespaces=self.ows_namespaces)
            layers.append(
                {
                    "layer_id": identifier.strip(),
                    "title": (title or identifier).strip(),
                    "abstract": abstract.strip() if abstract else None,
                }
            )
        return layers
