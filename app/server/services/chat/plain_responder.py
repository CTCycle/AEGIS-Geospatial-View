from __future__ import annotations

from server.services.llm.factory import LLMFactory
from server.services.llm.prompts import get_agent_response_prompt
from server.services.llm.types import LLMRequest


###############################################################################
class PlainResponder:

    # -------------------------------------------------------------------------
    def __init__(self, *, llm_factory: LLMFactory, provider: str, model: str) -> None:
        self.llm_factory = llm_factory
        self.provider = provider
        self.model = model

    # -------------------------------------------------------------------------
    def respond(self, user_text: str) -> str:
        provider = self.llm_factory.get_chat_provider(self.provider)
        result = provider.chat(
            LLMRequest(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": get_agent_response_prompt(
                            provider=self.provider, model=self.model
                        ),
                    },
                    {"role": "user", "content": user_text},
                ],
            )
        )
        return (result.content or "").strip() or ""
