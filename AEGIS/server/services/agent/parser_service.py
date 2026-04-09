from __future__ import annotations

import re

from AEGIS.server.domain.extraction.models import ExtractedIntent, ExtractedIntentPatch
from AEGIS.server.services.llm.factory import LLMFactory
from AEGIS.server.services.llm.prompts import AGENT_EXTRACTION_PROMPT
from AEGIS.server.services.llm.structured import INTENT_SCHEMA
from AEGIS.server.services.llm.types import ChatCompletionRequest

COORDINATE_PAIR_RE = re.compile(
    r"(?P<latitude>[+-]?\d{1,2}(?:\.\d+)?)\s*[, ]\s*(?P<longitude>[+-]?\d{1,3}(?:\.\d+)?)"
)


def _extract_coordinate_patch(user_message: str) -> ExtractedIntentPatch:
    match = COORDINATE_PAIR_RE.search(user_message)
    if not match:
        return ExtractedIntentPatch(user_goal=user_message.strip(), certainty=0.15)

    latitude = float(match.group("latitude"))
    longitude = float(match.group("longitude"))
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return ExtractedIntentPatch(user_goal=user_message.strip(), certainty=0.15)

    return ExtractedIntentPatch(
        coordinates={"latitude": latitude, "longitude": longitude},
        user_goal=user_message.strip(),
        certainty=0.9,
    )


class ParserService:
    def __init__(self, *, llm_factory: LLMFactory, provider: str, model: str) -> None:
        self.llm_factory = llm_factory
        self.provider = provider
        self.model = model

    def extract_patch(
        self,
        *,
        conversation_context: str,
        latest_state: ExtractedIntent,
        user_message: str,
    ) -> ExtractedIntentPatch:
        try:
            provider = self.llm_factory.get_parser_provider(self.provider)
            request = ChatCompletionRequest(
                model=self.model,
                messages=[
                    {"role": "system", "content": AGENT_EXTRACTION_PROMPT},
                    {
                        "role": "user",
                        "content": conversation_context,
                    },
                    {
                        "role": "user",
                        "content": (
                            "latest_state="
                            + str(latest_state.model_dump(mode="json"))
                            + "\nlatest_user_message="
                            + user_message
                        ),
                    },
                ],
            )
            payload = provider.structured_output(request, schema=INTENT_SCHEMA)
        except Exception:
            return _extract_coordinate_patch(user_message)
        if not isinstance(payload, dict):
            payload = {}
        return ExtractedIntentPatch.model_validate(payload)
