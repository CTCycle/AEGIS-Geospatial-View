from __future__ import annotations

import json
from typing import Any

from AEGIS.server.domain.agent.decision import AgentDecision
from AEGIS.server.domain.extraction.models import ExtractedIntent
from AEGIS.server.services.llm.factory import LLMFactory
from AEGIS.server.services.llm.prompts import AGENT_RESPONSE_PROMPT
from AEGIS.server.services.llm.types import ChatCompletionRequest

###############################################################################
class ChatResponseService:
    def __init__(self, *, llm_factory: LLMFactory, provider: str, model: str) -> None:
        self.llm_factory = llm_factory
        self.provider = provider
        self.model = model

    # -------------------------------------------------------------------------
    def generate(
        self,
        *,
        conversation_context: str,
        user_message: str,
        extracted_state: ExtractedIntent,
        decision: AgentDecision,
        retrieval: dict[str, list[dict[str, object]]],
        search_result: dict[str, Any] | None,
    ) -> str:
        try:
            provider = self.llm_factory.get_chat_provider(self.provider)
            payload = {
                "user_message": user_message,
                "extracted_state": extracted_state.model_dump(mode="json"),
                "decision": decision.model_dump(mode="json"),
                "retrieval": retrieval,
                "search_result": search_result,
            }
            result = provider.chat(
                ChatCompletionRequest(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": AGENT_RESPONSE_PROMPT},
                        {"role": "user", "content": conversation_context},
                        {"role": "user", "content": json.dumps(payload, default=str)},
                    ],
                )
            )
            text = (result.content or "").strip()
            if text:
                return text
        except Exception:
            pass

        if not decision.feasibility.is_supported:
            return (
                decision.feasibility.blocking_reason
                or "I can only help with location-based geospatial requests."
            )
        geocode_result = search_result.get("geocode_result") if isinstance(search_result, dict) else None
        if isinstance(geocode_result, dict):
            latitude = geocode_result.get("lat")
            longitude = geocode_result.get("lon")
            if latitude is not None and longitude is not None:
                return f"Coordinates: {latitude}, {longitude}."
            return "I could not resolve coordinates for that location."
        if search_result is not None:
            return "Search executed successfully."
        if decision.clarification_question:
            return decision.clarification_question
        return "I completed this geospatial turn."
