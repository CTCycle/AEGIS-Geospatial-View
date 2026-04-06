from __future__ import annotations

from AEGIS.server.domain.extraction.models import ExtractedIntent, ExtractedIntentPatch
from AEGIS.server.services.llm.factory import LLMFactory
from AEGIS.server.services.llm.prompts import PARSER_MODEL_SYSTEM_PROMPT
from AEGIS.server.services.llm.structured import INTENT_SCHEMA
from AEGIS.server.services.llm.types import ChatCompletionRequest


class ParserService:
    def __init__(self, *, llm_factory: LLMFactory, provider: str, model: str) -> None:
        self.llm_factory = llm_factory
        self.provider = provider
        self.model = model

    def extract_patch(self, *, latest_state: ExtractedIntent, user_message: str) -> ExtractedIntentPatch:
        provider = self.llm_factory.get_parser_provider(self.provider)
        request = ChatCompletionRequest(
            model=self.model,
            messages=[
                {"role": "system", "content": PARSER_MODEL_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "latest_state="
                        + str(latest_state.model_dump(mode="json"))
                        + "\nuser_message="
                        + user_message
                    ),
                },
            ],
        )
        payload = provider.structured_output(request, schema=INTENT_SCHEMA)
        if not isinstance(payload, dict):
            payload = {}
        return ExtractedIntentPatch.model_validate(payload)
