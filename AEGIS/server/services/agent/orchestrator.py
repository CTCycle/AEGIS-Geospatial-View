from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from AEGIS.server.domain.chat import ChatTurnRequest, ChatTurnResponse
from AEGIS.server.domain.geographics import LocationSearchRequest
from AEGIS.server.repositories.chat_history import ChatHistoryRepository
from AEGIS.server.repositories.model_settings import ModelSettingsRepository
from AEGIS.server.services.agent.executor import infer_datetime, requires_follow_up
from AEGIS.server.services.agent.prompts import AGENT_INTENT_SYSTEM_PROMPT
from AEGIS.server.services.chat.settings_service import ChatSettingsService
from AEGIS.server.services.llm.factory import LLMFactory
from AEGIS.server.services.llm.structured import parse_structured_json
from AEGIS.server.services.llm.types import ChatCompletionRequest
from AEGIS.server.services.search.intent_mapper import map_structured_intent_to_location_request
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
    ) -> None:
        self.search_orchestrator = search_orchestrator
        self.history_repo = history_repo or ChatHistoryRepository()
        self.settings_repo = settings_repo or ModelSettingsRepository()
        self.settings_service = settings_service or ChatSettingsService()
        self.llm_factory = llm_factory or LLMFactory()
        self.vector_retriever = vector_retriever or VectorRetriever()

    def _heuristic_intent(self, text: str, *, explicit_datetime: str | None) -> dict[str, Any]:
        coordinates_match = re.search(
            r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)",
            text,
        )
        coordinates = None
        if coordinates_match:
            coordinates = {
                "latitude": float(coordinates_match.group(1)),
                "longitude": float(coordinates_match.group(2)),
            }
        return {
            "location_text": text,
            "coordinates": coordinates,
            "search_radius_m": 2500.0,
            "representation_type": "map",
            "requested_overlays": [],
            "user_intent": "map_search",
            "datetime_inference": explicit_datetime or datetime.now(UTC).isoformat(),
            "missing_information": [],
            "should_execute_search": True,
            "follow_up_question": None,
        }

    def _extract_intent(self, text: str, *, explicit_datetime: str | None) -> dict[str, Any]:
        settings = self.settings_repo.get_or_create()
        provider = self.llm_factory.get_provider(settings.agent_model_provider)
        request = ChatCompletionRequest(
            model=settings.agent_model_name,
            messages=[
                {"role": "system", "content": AGENT_INTENT_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
        )
        try:
            payload = provider.structured_output(request, schema={})
            if payload:
                payload.setdefault("datetime_inference", explicit_datetime or infer_datetime(payload))
                return payload
        except Exception:
            pass
        return self._heuristic_intent(text, explicit_datetime=explicit_datetime)

    async def run_turn(self, request: ChatTurnRequest) -> ChatTurnResponse:
        session = self.history_repo.upsert_session(request.session_id, title=request.title)
        self.history_repo.append_message(
            session_id=session.id,
            role="user",
            content=request.message,
        )
        intent = self._extract_intent(request.message, explicit_datetime=request.datetime)
        retrieved = self.vector_retriever.retrieve_layers(request.message)
        intent["requested_overlays"] = list(
            dict.fromkeys(
                [*intent.get("requested_overlays", []), *retrieved.get("overlay_ids", [])]
            )
        )
        if requires_follow_up(intent):
            follow_up = str(intent.get("follow_up_question") or "Could you clarify the requested datetime?")
            self.history_repo.append_message(
                session_id=session.id,
                role="assistant",
                content=follow_up,
                structured_payload=intent,
            )
            return ChatTurnResponse(
                session_id=session.id,
                assistant_message=follow_up,
                structured_intent=intent,
                map_session=None,
                tool_payload={"execution": "follow_up"},
                follow_up_required=True,
            )

        mapped_payload = map_structured_intent_to_location_request(
            {
                **intent,
                "datetime": intent.get("datetime_inference") or datetime.now(UTC).isoformat(),
                "overlay_ids": intent.get("requested_overlays", []),
                "base_map": (retrieved.get("basemap_ids") or [None])[0],
            }
        )
        location_request = LocationSearchRequest.model_validate(mapped_payload)
        result = await self.search_orchestrator.execute(location_request)
        assistant_message = "Search executed successfully."
        self.history_repo.append_message(
            session_id=session.id,
            role="assistant",
            content=assistant_message,
            structured_payload=intent,
            tool_payload={"execution": "search"},
            map_session=result.get("map_session"),
        )
        return ChatTurnResponse(
            session_id=session.id,
            assistant_message=assistant_message,
            structured_intent=intent,
            map_session=result.get("map_session"),
            tool_payload=result.get("payload"),
            follow_up_required=False,
        )
