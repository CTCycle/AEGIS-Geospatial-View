from __future__ import annotations

from AEGIS.server.services.geospatial.catalog import GeospatialCatalogService
from AEGIS.server.services.geospatial.openaq import OpenAQService
from AEGIS.server.services.geospatial.pvgis import PVGISService
from AEGIS.server.services.search.planner import SearchPlanner
from AEGIS.server.services.search.query_service import QueryService
from AEGIS.server.services.vector.retriever import VectorRetriever


class _RetrieverStub(VectorRetriever):
    def retrieve_candidates(self, query: str, *, top_k: int = 8, basemap_k=None, overlay_k=None, provider_k=None):  # type: ignore[override]
        return {"basemaps": [], "overlays": [], "providers": []}


def test_query_service_missing_location_triggers_fallback() -> None:
    service = QueryService(
        planner=SearchPlanner(),
        retriever=_RetrieverStub(),
        catalog_service=GeospatialCatalogService(openaq_service=OpenAQService(), pvgis_service=PVGISService()),
    )
    result = service.process(
        intent={
            "user_goal": "show weather",
            "location": {"address": None, "city": None, "country": None},
            "coordinates": {"latitude": None, "longitude": None},
            "filters": [],
            "certainty": 0.1,
        },
        user_text="show weather",
        manifests={"basemaps": [], "overlays": [], "providers": []},
    )
    assert result.plan.should_execute is False
    assert result.plan.fallback_mode == "missing_location"
