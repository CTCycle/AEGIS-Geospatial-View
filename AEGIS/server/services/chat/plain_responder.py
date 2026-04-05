from __future__ import annotations

from AEGIS.server.services.llm.factory import LLMFactory
from AEGIS.server.services.llm.prompts import PLAIN_CHAT_PROMPT
from AEGIS.server.services.llm.types import ChatCompletionRequest


class PlainResponder:
    def __init__(self, *, llm_factory: LLMFactory, provider: str, model: str) -> None:
        self.llm_factory = llm_factory
        self.provider = provider
        self.model = model

    def respond(self, user_text: str) -> str:
        provider = self.llm_factory.get_chat_provider(self.provider)
        result = provider.chat(
            ChatCompletionRequest(
                model=self.model,
                messages=[
                    {"role": "system", "content": PLAIN_CHAT_PROMPT},
                    {"role": "user", "content": user_text},
                ],
            )
        )
        return (result.content or "").strip() or ""
