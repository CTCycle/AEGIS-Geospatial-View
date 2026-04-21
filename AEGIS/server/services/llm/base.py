from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol

from AEGIS.server.services.llm.types import (
    ChatCompletionRequest,
    ChatCompletionResult,
    ModelDescriptor,
)

###############################################################################
class LLMProvider(Protocol):
    provider_name: str

    def list_models(self) -> list[ModelDescriptor]: ...

    def chat(self, request: ChatCompletionRequest) -> ChatCompletionResult: ...

    def stream_chat(self, request: ChatCompletionRequest) -> Iterable[str]: ...

    def structured_output(
        self, request: ChatCompletionRequest, schema: type[object]
    ) -> dict[str, Any]: ...

    def embeddings(self, *, model: str, input_text: str) -> list[float]: ...

    def health_check(self) -> dict[str, Any]: ...
