from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from AEGIS.server.domain.chat import ChatTurnRequest, ChatTurnResponse
from AEGIS.server.domain.geographics import LocationSearchRequest
from AEGIS.server.repositories.chat_history import ChatHistoryRepository
from AEGIS.server.repositories.model_settings import ModelSettingsRepository
from AEGIS.server.services.agent.intent_extractor import IntentExtractor
from AEGIS.server.services.agent.response_generator import AgentResponseGenerator
from AEGIS.server.services.chat.settings_service import ChatSettingsService
from AEGIS.server.services.geospatial.catalog import GeospatialCatalogService
from AEGIS.server.services.geospatial.manifest_loader import GeospatialManifestLoader
from AEGIS.server.services.geospatial.openaq import OpenAQService
from AEGIS.server.services.geospatial.pvgis import PVGISService
from AEGIS.server.services.llm.factory import LLMFactory
from AEGIS.server.services.search.intent_mapper import map_structured_intent_to_location_request
from AEGIS.server.services.search.planner import SearchPlanner
from AEGIS.server.services.search.query_service import QueryService
from AEGIS.server.services.search.orchestrator import LocationSearchOrchestrator
from AEGIS.server.services.vector.retriever import VectorRetriever


class AgentOrchestrator:
    def __init__(
        self,
        *,
        search_orchestrator: LocationSearchOrchestrator,
        history_repo: ChatHistoryRepository | None = None,
        settings_repo: ModelSettingsRepository | None = None,
        settings_service: ChatSettingsService | None = None,
        llm_factory: LLMFactory | None = None,
        vector_retriever: VectorRetriever | None = None,
        planner: SearchPlanner | None = None,
        manifest_loader: GeospatialManifestLoader | None = None,
    ) -> None:
        self.search_orchestrator = search_orchestrator
        self.history_repo = history_repo or ChatHistoryRepository()
        self.settings_repo = settings_repo or ModelSettingsRepository()
        self.settings_service = settings_service or ChatSettingsService()
        self.llm_factory = llm_factory or LLMFactory()
        self.vector_retriever = vector_retriever or VectorRetriever()
        self.planner = planner or SearchPlanner()
        self.manifest_loader = manifest_loader or GeospatialManifestLoader()
        self.catalog_service = GeospatialCatalogService(openaq_service=OpenAQService(), pvgis_service=PVGISService())

    def extract_intent(self, text: str, *, explicit_datetime: str | None) -> dict[str, Any]:
        settings = self.settings_repo.get_or_create()
        extractor = IntentExtractor(
            llm_factory=self.llm_factory,
            provider=settings.agent_model_provider,
            model=settings.agent_model_name,
        )
        try:
            return extractor.extract(text, explicit_datetime=explicit_datetime)
        except Exception:
            return {
                "request_text": text,
                "location": {"name": text, "coordinates": None, "bbox": None, "granularity": None, "is_partial": False, "ambiguity_reason": None},
                "map_preferences": {
                    "map_type": "auto",
                    "map_type_confidence": 0.0,
                    "basemap_preference": None,
                    "overlay_candidates": [],
                },
                "task": {
                    "user_intent": "map_search",
                    "scope": "missing_area",
                    "requires_external_fact_finding": False,
                    "is_geographically_actionable": False,
                },
                "temporal_context": {
                    "raw_text": None,
                    "normalized_datetime": explicit_datetime or datetime.now(UTC).isoformat(),
                    "date_range": None,
                },
                "planning": {
                    "confidence": 0.0,
                    "missing_information": ["location"],
                    "should_execute_search": False,
                    "follow_up_question": "Which location should I inspect on the map?",
                    "fallback_mode": "missing_location",
                },
            }

    async def run_turn(self, request: ChatTurnRequest) -> ChatTurnResponse:
        session = self.history_repo.upsert_session(request.session_id, title=request.title)
        self.history_repo.append_message(session_id=session.id, role="user", content=request.message)

        intent = self.extract_intent(request.message, explicit_datetime=request.datetime)
        query_service = QueryService(
            planner=self.planner,
            retriever=self.vector_retriever,
            catalog_service=self.catalog_service,
        )
        query = query_service.process(intent=intent, user_text=request.message, manifests=self.manifest_loader.load_all())
        intent = query.intent
        plan = query.plan

        execution = "follow_up"
        map_session: dict[str, Any] | None = None
        tool_payload: dict[str, Any] | None = None

        if plan.should_execute:
            mapped_payload = map_structured_intent_to_location_request(
                {
                    **intent,
                    "datetime": intent.get("temporal_context", {}).get("normalized_datetime") or datetime.now(UTC).isoformat(),
                    "overlay_ids": plan.selected_overlay_ids,
                    "base_map": plan.selected_basemap_id,
                }
            )
            location_request = LocationSearchRequest.model_validate(mapped_payload)
            result = await self.search_orchestrator.execute(location_request)
            map_session = result.get("map_session")
            tool_payload = result.get("payload")
            execution = "search"
        else:
            map_session = plan.preview_map_session
            tool_payload = {"execution": "follow_up", "fallback_mode": plan.fallback_mode}

        settings = self.settings_repo.get_or_create()
        responder = AgentResponseGenerator(
            llm_factory=self.llm_factory,
            provider=settings.agent_model_provider,
            model=settings.agent_model_name,
        )
        follow_up_question = intent.get("planning", {}).get("follow_up_question") if isinstance(intent.get("planning"), dict) else None
        assistant_message = responder.generate(
            user_message=request.message,
            intent=intent,
            retrieval=query.retrieval,
            execution=execution,
            map_session=map_session,
            follow_up_question=str(follow_up_question) if follow_up_question else None,
        )

        follow_up_required = not plan.should_execute
        self.history_repo.append_message(
            session_id=session.id,
            role="assistant",
            content=assistant_message,
            structured_payload=intent,
            tool_payload=tool_payload,
            map_session=map_session,
        )
        return ChatTurnResponse(
            session_id=session.id,
            assistant_message=assistant_message,
            structured_intent=intent,
            map_session=map_session,
            tool_payload=tool_payload,
            follow_up_required=follow_up_required,
            fallback_mode=plan.fallback_mode,
        )
