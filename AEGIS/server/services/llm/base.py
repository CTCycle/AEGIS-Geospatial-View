from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol

from AEGIS.server.services.llm.types import (
    LLMRequest,
    LLMResult,
    ModelDescriptor,
)

###############################################################################
class LLMProvider(Protocol):
    provider_name: str

    def list_models(self) -> list[ModelDescriptor]: ...

    def chat(self, request: LLMRequest) -> LLMResult: ...

    def stream_chat(self, request: LLMRequest) -> Iterable[str]: ...

    def structured_output(
        self, request: LLMRequest, schema: type[object]
    ) -> dict[str, Any]: ...

    def embeddings(self, *, model: str, input_text: str) -> list[float]: ...

    def health_check(self) -> dict[str, Any]: ...
