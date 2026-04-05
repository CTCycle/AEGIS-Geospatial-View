from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from AEGIS.server.services.geospatial.catalog import GeospatialCatalogService
from AEGIS.server.services.search.fallbacks import build_preview_map_session
from AEGIS.server.services.search.map_type_resolver import MapTypeResolver
from AEGIS.server.services.search.planner import SearchPlan, SearchPlanner
from AEGIS.server.services.search.scope_validator import ScopeValidator
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
        scope_validator: ScopeValidator | None = None,
        map_type_resolver: MapTypeResolver | None = None,
    ) -> None:
        self.planner = planner
        self.retriever = retriever
        self.catalog_service = catalog_service
        self.scope_validator = scope_validator or ScopeValidator()
        self.map_type_resolver = map_type_resolver or MapTypeResolver()

    def process(self, *, intent: dict[str, Any], user_text: str, manifests: dict[str, list[dict[str, Any]]]) -> QueryServiceResult:
        scope = self.scope_validator.validate(intent)
        map_type_resolution = self.map_type_resolver.resolve(intent=intent, user_text=user_text)
        intent.setdefault("map_preferences", {})
        intent["map_preferences"]["map_type"] = map_type_resolution.map_type
        intent["map_preferences"]["map_type_source"] = map_type_resolution.source

        dynamic_top_k = self._compute_top_k(intent)
        retrieval = self.retriever.retrieve_candidates(user_text, top_k=dynamic_top_k)
        plan = self.planner.plan(intent=intent, retrieval=retrieval, manifests=manifests)

        if not scope.is_actionable:
            plan.should_execute = False
            plan.fallback_mode = scope.reason or "needs_clarification"
            plan.clarification_needed = True
            plan.preview_location = intent.get("location", {})
            plan.preview_basemap_id = "osm_default"
            plan.preview_overlay_ids = []
            plan.follow_up_reason = scope.reason
            plan.preview_map_session = build_preview_map_session(
                catalog_service=self.catalog_service,
                location=intent.get("location", {}),
                reason=plan.fallback_mode,
            )
        elif plan.fallback_mode == "partial_location":
            plan.preview_map_session = build_preview_map_session(
                catalog_service=self.catalog_service,
                location=intent.get("location", {}),
                reason=plan.fallback_mode,
            )

        return QueryServiceResult(plan=plan, retrieval=retrieval, intent=intent)

    def _compute_top_k(self, intent: dict[str, Any]) -> int:
        prefs = intent.get("map_preferences") if isinstance(intent.get("map_preferences"), dict) else {}
        overlays = prefs.get("overlay_candidates") if isinstance(prefs.get("overlay_candidates"), list) else []
        text = str(intent.get("request_text") or "").lower()
        if len(overlays) >= 3 or ("weather" in text and "traffic" in text):
            return 14
        if overlays:
            return 10
        return 6
