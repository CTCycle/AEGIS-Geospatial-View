from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from AEGIS.server.services.geospatial.catalog import GeospatialCatalogService
from AEGIS.server.services.search.planner import SearchPlan, SearchPlanner
from AEGIS.server.services.vector.retriever import VectorRetriever


@dataclass(slots=True)
class QueryServiceResult:
    plan: SearchPlan
    retrieval: dict[str, list[dict[str, object]]]
    intent: dict[str, Any]


class QueryService:
    def __init__(
        self,
        *,
        planner: SearchPlanner,
        retriever: VectorRetriever,
        catalog_service: GeospatialCatalogService,
    ) -> None:
        self.planner = planner
        self.retriever = retriever
        self.catalog_service = catalog_service

    def process(self, *, intent: dict[str, Any], user_text: str, manifests: dict[str, list[dict[str, Any]]]) -> QueryServiceResult:
        retrieval = self.retriever.retrieve_candidates(self._build_retrieval_query(intent, user_text), top_k=10)
        plan = self.planner.plan(intent=intent, retrieval=retrieval, manifests=manifests)
        return QueryServiceResult(plan=plan, retrieval=retrieval, intent=intent)

    def _build_retrieval_query(self, intent: dict[str, Any], user_text: str) -> str:
        location = intent.get("location") if isinstance(intent.get("location"), dict) else {}
        filters = intent.get("filters") if isinstance(intent.get("filters"), list) else []
        return " ".join(
            [
                user_text,
                str(intent.get("user_goal") or ""),
                " ".join(str(item) for item in filters),
                str(intent.get("base_map_type") or ""),
                str(intent.get("area_of_interest") or ""),
                str(location.get("address") or ""),
                str(location.get("city") or ""),
                str(location.get("country") or ""),
            ]
        ).strip()
