from __future__ import annotations

from server.domain.geographics import (
    GeospatialCatalogResponse,
    LocationSearchRequest,
    SearchByLocationResponse,
)
from server.services.geospatial.catalog import GeospatialCatalogService
from server.services.geospatial.osm_tiles import OsmTileProxyError, OsmTileProxyService
from server.services.search.errors import MapSearchTileProxyError
from server.services.search.orchestrator import LocationSearchOrchestrator
from server.common.constants import MAP_SEARCH_STATUS_MESSAGE


class MapSearchExecutionService:
    def __init__(
        self,
        *,
        orchestrator: LocationSearchOrchestrator,
        catalog_service: GeospatialCatalogService,
        osm_tile_proxy_service: OsmTileProxyService,
    ) -> None:
        self.orchestrator = orchestrator
        self.catalog_service = catalog_service
        self.osm_tile_proxy_service = osm_tile_proxy_service

    async def search_by_location(self, payload: LocationSearchRequest) -> SearchByLocationResponse:
        map_session = await self.orchestrator.execute(payload)
        return SearchByLocationResponse(
            status_message=MAP_SEARCH_STATUS_MESSAGE,
            map_session=map_session,
        )

    async def get_catalog(self) -> GeospatialCatalogResponse:
        catalog = self.catalog_service.list_catalog()
        return GeospatialCatalogResponse.model_validate(catalog)

    def fetch_osm_basemap_tile(self, z: int, x: int, y: int) -> tuple[bytes, str, str]:
        try:
            return self.osm_tile_proxy_service.fetch_tile(z, x, y)
        except OsmTileProxyError as exc:
            raise MapSearchTileProxyError(str(exc)) from exc

