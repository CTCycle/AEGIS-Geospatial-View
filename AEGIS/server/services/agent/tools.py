from __future__ import annotations

from AEGIS.server.services.geospatial.catalog import GeospatialCatalogService
from AEGIS.server.services.geospatial.normatim import NormatimService
from AEGIS.server.services.search.orchestrator import LocationSearchOrchestrator

###############################################################################
class AgentTools:
    def __init__(
        self,
        *,
        normatim_service: NormatimService,
        catalog_service: GeospatialCatalogService,
        search_orchestrator: LocationSearchOrchestrator,
    ) -> None:
        self.nomatim_service = normatim_service
        self.catalog_service = catalog_service
        self.search_orchestrator = search_orchestrator
