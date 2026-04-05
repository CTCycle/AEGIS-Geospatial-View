from __future__ import annotations

from typing import Any

from AEGIS.server.services.llm.factory import LLMFactory
from AEGIS.server.services.llm.prompts import AGENT_RESPONSE_PROMPT
from AEGIS.server.services.llm.types import ChatCompletionRequest


class AgentResponseGenerator:
    def __init__(self, *, llm_factory: LLMFactory, provider: str, model: str) -> None:
        self.llm_factory = llm_factory
        self.provider = provider
        self.model = model

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
        try:
            provider = self.llm_factory.get_agent_provider(self.provider)
            prompt_payload = {
                "user_message": user_message,
                "intent": intent,
                "retrieval": retrieval,
                "execution": execution,
                "map_session": map_session,
                "follow_up_question": follow_up_question,
            }
            result = provider.chat(
                ChatCompletionRequest(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": AGENT_RESPONSE_PROMPT},
                        {"role": "user", "content": str(prompt_payload)},
                    ],
                )
            )
            text = (result.content or "").strip()
            if text:
                return text
        except Exception:
            pass
        if follow_up_question:
            return follow_up_question
        return "I processed the geospatial request."
