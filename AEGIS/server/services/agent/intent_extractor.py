from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from AEGIS.server.domain.extraction.models import ExtractedIntent
from AEGIS.server.domain.extraction.patching import merge_extracted_intent
from AEGIS.server.services.agent.parser_service import ParserService
from AEGIS.server.services.llm.context_builder import build_conversation_context
from AEGIS.server.services.llm.factory import LLMFactory
from AEGIS.server.services.llm.structured import normalize_structured_payload


class IntentExtractor:
    def __init__(self, *, llm_factory: LLMFactory, provider: str, model: str) -> None:
        self.parser_service = ParserService(
            llm_factory=llm_factory, provider=provider, model=model
        )

    def extract(
        self, text: str, explicit_datetime: str | None = None
    ) -> dict[str, Any]:
        baseline = ExtractedIntent()
        context = build_conversation_context(
            messages=[{"role": "user", "content": text}],
            extracted_info=baseline.model_dump_json(indent=2),
        )
        patch = self.parser_service.extract_patch(
            conversation_context=context,
            latest_state=baseline,
            user_message=text,
        )
        merged = merge_extracted_intent(baseline, patch)
        normalized = normalize_structured_payload(merged.model_dump(mode="json"))
        normalized["normalized_datetime"] = (
            explicit_datetime or datetime.now(UTC).isoformat()
        )
        return normalized
