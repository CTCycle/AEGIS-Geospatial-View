from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from AEGIS.server.configurations import server_settings
from AEGIS.server.domain.chat import ChatTurnRequest, ChatTurnResponse
from AEGIS.server.domain.extraction.models import ExtractedIntent
from AEGIS.server.domain.extraction.patching import merge_extracted_intent
from AEGIS.server.domain.geographics import LocationSearchRequest
from AEGIS.server.repositories.chat_history import ChatHistoryRepository
from AEGIS.server.repositories.model_settings import ModelSettingsRepository
from AEGIS.server.repositories.session_catalog import SessionCatalogRepository
from AEGIS.server.repositories.session_details import SessionDetailsRepository
from AEGIS.server.services.agent.chat_response_service import ChatResponseService
from AEGIS.server.services.agent.decision_service import DecisionService
from AEGIS.server.services.agent.parser_service import ParserService
from AEGIS.server.services.agent.tools import AgentTools
from AEGIS.server.services.chat.history_buffer import ChatHistoryBuffer
from AEGIS.server.services.geospatial.manifest_loader import GeospatialManifestLoader
from AEGIS.server.services.llm.factory import LLMFactory
from AEGIS.server.services.llm.context_builder import build_conversation_context
from AEGIS.server.services.search.intent_mapper import map_structured_intent_to_location_request
from AEGIS.server.services.search.orchestrator import LocationSearchOrchestrator
from AEGIS.server.services.vector.retriever import VectorRetriever

###############################################################################
class AgentOrchestrator:
    def __init__(
        self,
        *,
        search_orchestrator: LocationSearchOrchestrator,
        history_repo: ChatHistoryRepository | None = None,
        history_buffer: ChatHistoryBuffer | None = None,
        settings_repo: ModelSettingsRepository | None = None,
        llm_factory: LLMFactory | None = None,
        vector_retriever: VectorRetriever | None = None,
        manifest_loader: GeospatialManifestLoader | None = None,
        session_catalog_repo: SessionCatalogRepository | None = None,
        session_details_repo: SessionDetailsRepository | None = None,
        agent_tools: AgentTools | None = None,
    ) -> None:
        self.search_orchestrator = search_orchestrator
        self.history_repo = history_repo or ChatHistoryRepository()
        self.history_buffer = history_buffer or ChatHistoryBuffer(history_repo=self.history_repo)
        self.settings_repo = settings_repo or ModelSettingsRepository()
        self.llm_factory = llm_factory or LLMFactory()
        self.vector_retriever = vector_retriever or VectorRetriever()
        self.manifest_loader = manifest_loader or GeospatialManifestLoader()
        self.session_catalog_repo = session_catalog_repo or SessionCatalogRepository()
        self.session_details_repo = session_details_repo or SessionDetailsRepository()
        self.agent_tools = agent_tools
        nominatim_service = getattr(self.search_orchestrator, "nominatim_service", None)
        catalog_service = getattr(self.search_orchestrator, "catalog_service", None)
        if self.agent_tools is None and nominatim_service is not None and catalog_service is not None:
            self.agent_tools = AgentTools(
                nominatim_service=nominatim_service,
                catalog_service=catalog_service,
                search_orchestrator=self.search_orchestrator,
            )

    def _build_retrieval_query(self, *, user_message: str, state: ExtractedIntent) -> str:
        latest_request = user_message.strip()
        resolved_location = ", ".join(
            item
            for item in [
                state.location.address,
                state.location.city,
                state.location.country,
            ]
            if item
        )
        context_terms = " ".join(
            item
            for item in [
                state.user_goal.strip(),
                " ".join(state.filters),
                state.base_map_type or "",
                state.area_of_interest or "",
            ]
            if item
        )
        return " | ".join(
            segment
            for segment in [
                latest_request,
                f"resolved location: {resolved_location}" if resolved_location else "",
                f"context: {context_terms}" if context_terms else "",
            ]
            if segment
        )

    async def run_turn(self, request: ChatTurnRequest) -> ChatTurnResponse:
        started = perf_counter()
        settings = self.settings_repo.get_or_create()
        session = self.history_repo.upsert_session(request.session_id, title=request.title)
        user_row = self.history_repo.append_message(session_id=session.id, role="user", content=request.message)
        self.history_buffer.append(
            session.id,
            {
                "id": user_row.id,
                "session_id": session.id,
                "turn_index": user_row.turn_index,
                "role": user_row.role,
                "content": user_row.content,
                "structured_payload": None,
                "tool_payload": None,
                "map_session": None,
                "created_at": user_row.created_at.isoformat() if user_row.created_at else None,
            },
        )

        _history = self.history_buffer.get_or_hydrate(session.id)
        latest_state = self.history_repo.get_latest_extracted_state(session.id) or ExtractedIntent()
        latest_extracted_info = latest_state.model_dump_json(indent=2)
        initial_context = build_conversation_context(
            messages=_history,
            extracted_info=latest_extracted_info,
            max_messages=server_settings.chat.max_history_messages,
        )

        parser_service = ParserService(
            llm_factory=self.llm_factory,
            provider=settings.parser_model_provider,
            model=settings.parser_model_name,
        )
        decision_service = DecisionService(
            llm_factory=self.llm_factory,
            provider=settings.agent_model_provider,
            model=settings.agent_model_name,
        )
        chat_service = ChatResponseService(
            llm_factory=self.llm_factory,
            provider=settings.chat_model_provider,
            model=settings.chat_model_name,
        )

        patch = parser_service.extract_patch(
            conversation_context=initial_context,
            latest_state=latest_state,
            user_message=request.message,
        )
        extracted_state = merge_extracted_intent(latest_state, patch)
        merged_extracted_info = extracted_state.model_dump_json(indent=2)
        context = build_conversation_context(
            messages=_history,
            extracted_info=merged_extracted_info,
            max_messages=server_settings.chat.max_history_messages,
        )

        retrieval_query = self._build_retrieval_query(user_message=request.message, state=extracted_state)
        retrieval = self.vector_retriever.retrieve_candidates(retrieval_query, top_k=10)
        decision = decision_service.decide(
            conversation_context=context,
            user_message=request.message,
            extracted_state=extracted_state,
            retrieval=retrieval,
        )

        search_result: dict[str, Any] | None = None
        map_session: dict[str, Any] | None = None
        tool_payload: dict[str, Any] | None = None
        if decision.execution_mode == "search" and decision.should_trigger_search:
            mapped_payload = map_structured_intent_to_location_request(
                extracted_state=extracted_state.model_dump(mode="json"),
                user_message=request.message,
                selected_basemap_id=decision.selected_basemap_id,
                selected_overlay_ids=decision.selected_overlay_ids,
                fallback_datetime=request.datetime or datetime.now(UTC).isoformat(),
            )
            location_request = LocationSearchRequest.model_validate(mapped_payload)
            search_result = await self.search_orchestrator.execute(location_request)
            map_session = search_result.get("map_session")
            tool_payload = search_result.get("payload")
        elif decision.execution_mode == "geocode":
            geocode_result = (
                await self.agent_tools.geocode_location(
                    address=extracted_state.location.address,
                    city=extracted_state.location.city,
                    country_name=extracted_state.location.country,
                )
                if self.agent_tools is not None
                else None
            )
            search_result = {"geocode_result": geocode_result}
            tool_payload = {
                "execution": "location_to_coordinates",
                "result": geocode_result,
            }
        elif decision.execution_mode == "clarify":
            tool_payload = {"execution": "follow_up", "fallback_mode": "missing_location"}

        assistant_message = chat_service.generate(
            conversation_context=context,
            user_message=request.message,
            extracted_state=extracted_state,
            decision=decision,
            retrieval=retrieval,
            search_result=search_result,
        )
        assistant_row = self.history_repo.append_message(
            session_id=session.id,
            role="assistant",
            content=assistant_message,
            structured_payload=extracted_state.model_dump(mode="json"),
            tool_payload=tool_payload,
            map_session=map_session,
        )
        self.history_buffer.append(
            session.id,
            {
                "id": assistant_row.id,
                "session_id": session.id,
                "turn_index": assistant_row.turn_index,
                "role": assistant_row.role,
                "content": assistant_row.content,
                "structured_payload": extracted_state.model_dump(mode="json"),
                "tool_payload": tool_payload,
                "map_session": map_session,
                "created_at": assistant_row.created_at.isoformat() if assistant_row.created_at else None,
            },
        )

        elapsed = perf_counter() - started
        self.session_catalog_repo.upsert_for_session(
            session_id=session.id,
            models={
                "parser": {"provider": settings.parser_model_provider, "name": settings.parser_model_name},
                "agent": {"provider": settings.agent_model_provider, "name": settings.agent_model_name},
                "chat": {"provider": settings.chat_model_provider, "name": settings.chat_model_name},
            },
        )
        self.session_details_repo.insert_turn(
            session_id=session.id,
            message_id=assistant_row.id,
            user_message=request.message,
            chat_response=assistant_message,
            extracted_info=extracted_state.model_dump(mode="json"),
            response_time=elapsed,
            has_triggered_search=decision.should_trigger_search,
        )

        follow_up_required = decision.execution_mode == "clarify" or decision.decision == "search_with_follow_up"
        fallback_mode = "needs_clarification" if follow_up_required else "none"
        return ChatTurnResponse(
            session_id=session.id,
            assistant_message=assistant_message,
            structured_intent=extracted_state.model_dump(mode="json"),
            extracted_state=extracted_state.model_dump(mode="json"),
            map_session=map_session,
            tool_payload=tool_payload,
            follow_up_required=follow_up_required,
            fallback_mode=fallback_mode,
        )
