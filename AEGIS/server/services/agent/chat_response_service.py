from __future__ import annotations

import json
from typing import Any

from AEGIS.server.domain.agent.decision import AgentDecision
from AEGIS.server.domain.extraction.models import ExtractedIntent
from AEGIS.server.services.llm.factory import LLMFactory
from AEGIS.server.services.llm.prompts import CHAT_RESPONSE_SYSTEM_PROMPT
from AEGIS.server.services.llm.types import ChatCompletionRequest


class ChatResponseService:
    def __init__(self, *, llm_factory: LLMFactory, provider: str, model: str) -> None:
        self.llm_factory = llm_factory
        self.provider = provider
        self.model = model

    def generate(
        self,
        *,
        user_message: str,
        extracted_state: ExtractedIntent,
        decision: AgentDecision,
        retrieval: dict[str, list[dict[str, object]]],
        search_result: dict[str, Any] | None,
    ) -> str:
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
                    {"role": "system", "content": CHAT_RESPONSE_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(payload)},
                ],
            )
        )
        text = (result.content or "").strip()
        if text:
            return text
        if decision.clarification_question:
            return decision.clarification_question
        return "I completed this geospatial turn."
