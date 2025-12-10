from __future__ import annotations

import copy
import json
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from tqdm import tqdm

from AEGIS.server.utils.configurations import server_settings
from AEGIS.server.utils.logger import logger
from AEGIS.server.utils.repository.serializer import DataSerializer

TILE_MATRIX_SET_TO_RESOLUTION_M: dict[str, float] = {
    "15.625m": 15.625,
    "31.25m": 31.25,
    "250m": 250.0,
    "500m": 500.0,
    "1km": 1000.0,
    "1.5km": 1500.0,
    "2km": 2000.0,
    "GoogleMapsCompatible_Level6": 2445.98490512564,
    "GoogleMapsCompatible_Level7": 1222.99245256282,
    "GoogleMapsCompatible_Level8": 611.49622628141,
    "GoogleMapsCompatible_Level9": 305.748113140705,
    "GoogleMapsCompatible_Level12": 38.21851414258813,
    "GoogleMapsCompatible_Level13": 19.109257071294063,
}


type LayerPayload = dict[str, str | None | list[str] | list[float]]


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
    tile_matrix_sets: set[str]


###############################################################################
class GIBSLayersUpdater:
    def __init__(
        self,
        serializer: DataSerializer | None = None,
        endpoints: dict[str, str] | None = None,
        user_agent: str | None = None,
        ows_namespaces: dict[str, str] | None = None,
        request_timeout: float | None = None,
        retry_backoff_s: float | None = None,
        max_attempts: int | None = None,
    ) -> None:
        self.serializer = serializer or DataSerializer()
        settings = server_settings.gibs
        self.endpoints = copy.deepcopy(endpoints or settings.capabilities_endpoints)
        self.ows_namespaces = copy.deepcopy(ows_namespaces or settings.ows_namespaces)
        self.user_agent = user_agent or settings.layer_sync_user_agent
        self.request_timeout = request_timeout or settings.layer_sync_timeout
        self.retry_backoff_s = (
            retry_backoff_s if retry_backoff_s is not None else settings.retry_backoff_s
        )
        attempts = max_attempts if max_attempts is not None else 3
        self.max_attempts = attempts if attempts > 0 else 1

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
                        tile_matrix_sets=set(),
                    )
                    aggregated[layer_id] = entry
                if layer["title"] and entry.title == entry.layer_id:
                    entry.title = layer["title"]
                if layer["abstract"]:
                    entry.abstract = layer["abstract"]
                entry.projections.add(projection)
                entry.source_urls.add(url)
                entry.tile_matrix_sets.update(layer["tile_matrix_sets"])

        normalized: list[LayerPayload] = []
        for snapshot in aggregated.values():
            resolutions = self.resolve_meters_per_pixel(snapshot.tile_matrix_sets)
            normalized.append(
                {
                    "layer_id": snapshot.layer_id,
                    "title": snapshot.title,
                    "abstract": snapshot.abstract,
                    "projections": json.dumps(sorted(snapshot.projections)),
                    "source_urls": json.dumps(sorted(snapshot.source_urls)),
                    "tile_matrix_sets": json.dumps(sorted(snapshot.tile_matrix_sets)),
                    "meters_per_pixel": (
                        json.dumps(resolutions) if resolutions else None
                    ),
                }
            )
        return normalized

    # -------------------------------------------------------------------------
    def resolve_meters_per_pixel(self, tile_matrix_sets: set[str]) -> list[float]:
        resolutions: list[float] = []
        for tile_matrix in sorted(tile_matrix_sets):
            resolved = TILE_MATRIX_SET_TO_RESOLUTION_M.get(tile_matrix)
            if resolved is not None:
                resolutions.append(resolved)
        return resolutions

    # -------------------------------------------------------------------------
    def fetch_capabilities(self, url: str) -> bytes:
        request = Request(url, headers={"User-Agent": self.user_agent})
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                with urlopen(request, timeout=self.request_timeout) as response:
                    return response.read()
            except (HTTPError, URLError, TimeoutError) as exc:  # pragma: no cover
                last_error = exc
                if attempt < self.max_attempts - 1:
                    delay = self.compute_backoff_delay(attempt)
                    logger.warning(
                        (
                            "Capabilities fetch failed (%s/%s) for %s: %s. "
                            "Retrying in %.1fs."
                        ),
                        attempt + 1,
                        self.max_attempts,
                        url,
                        exc,
                        delay,
                    )
                    time.sleep(delay)
                    continue
        raise LayerHarvestError(
            f"Failed to download capabilities at {url} after {self.max_attempts} attempts"
        ) from last_error

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
            tile_matrix_sets = self.parse_tile_matrix_sets(layer)
            layers.append(
                {
                    "layer_id": identifier.strip(),
                    "title": (title or identifier).strip(),
                    "abstract": abstract.strip() if abstract else None,
                    "tile_matrix_sets": tile_matrix_sets,
                }
            )
        return layers

    # -------------------------------------------------------------------------
    def parse_tile_matrix_sets(self, layer: ElementTree.Element) -> list[str]:
        matrix_sets: set[str] = set()
        for entry in layer.findall(".//{*}TileMatrixSetLink/{*}TileMatrixSet"):
            if not entry.text:
                continue
            identifier = entry.text.strip()
            if identifier:
                matrix_sets.add(identifier)
        return sorted(matrix_sets)

    # -------------------------------------------------------------------------
    def compute_backoff_delay(self, attempt: int) -> float:
        return self.retry_backoff_s * (2**attempt)
