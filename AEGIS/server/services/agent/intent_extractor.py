from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from AEGIS.server.services.agent.prompts import AGENT_INTENT_SYSTEM_PROMPT
from AEGIS.server.services.llm.factory import LLMFactory
from AEGIS.server.services.llm.structured import INTENT_SCHEMA, normalize_structured_payload
from AEGIS.server.services.llm.types import ChatCompletionRequest


class IntentExtractor:
    def __init__(self, *, llm_factory: LLMFactory, provider: str, model: str) -> None:
        self.llm_factory = llm_factory
        self.provider = provider
        self.model = model

    def extract(self, text: str, explicit_datetime: str | None = None) -> dict[str, Any]:
        provider = self.llm_factory.get_agent_provider(self.provider)
        request = ChatCompletionRequest(
            model=self.model,
            messages=[
                {"role": "system", "content": AGENT_INTENT_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
        )
        payload = provider.structured_output(request, schema=INTENT_SCHEMA)
        normalized = normalize_structured_payload(payload if isinstance(payload, dict) else {})
        normalized.setdefault("temporal_context", {})
        normalized["temporal_context"]["normalized_datetime"] = explicit_datetime or normalized["temporal_context"].get("normalized_datetime") or datetime.now(UTC).isoformat()
        return normalized
