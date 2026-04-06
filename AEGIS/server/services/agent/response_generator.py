from __future__ import annotations

from typing import Any

from AEGIS.server.domain.agent.decision import AgentDecision
from AEGIS.server.domain.extraction.models import ExtractedIntent
from AEGIS.server.services.agent.chat_response_service import ChatResponseService
from AEGIS.server.services.llm.factory import LLMFactory


class AgentResponseGenerator:
    def __init__(self, *, llm_factory: LLMFactory, provider: str, model: str) -> None:
        self.chat_service = ChatResponseService(llm_factory=llm_factory, provider=provider, model=model)

    def generate(
        self,
        *,
        user_message: str,
        intent: dict[str, Any],
        retrieval: dict[str, list[dict[str, object]]],
        execution: str,
        map_session: dict[str, Any] | None,
        follow_up_question: str | None,
    ) -> str:
        decision = AgentDecision(
            decision="search_and_complete" if execution == "search" else "clarify",
            should_trigger_search=execution == "search",
            location_status="valid" if execution == "search" else "partial",
            requires_geocoding=False,
            clarification_question=follow_up_question,
        )
        extracted_state = ExtractedIntent.model_validate(intent)
        return self.chat_service.generate(
            user_message=user_message,
            extracted_state=extracted_state,
            decision=decision,
            retrieval=retrieval,
            search_result={"map_session": map_session} if map_session else None,
        )
