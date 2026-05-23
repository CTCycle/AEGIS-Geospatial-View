from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, Protocol

from server.services.llm.types import (
    LLMRequest,
    LLMResult,
    LLMToolDefinition,
    ModelDescriptor,
)

###############################################################################
class LLMProvider(Protocol):
    provider_name: str

    def list_models(self) -> list[ModelDescriptor]: ...

    def chat(
        self,
        request: LLMRequest,
        *,
        tools: Sequence[LLMToolDefinition] | None = None,
        tool_choice: str | None = "auto",
        response_json_schema: dict[str, Any] | None = None,
    ) -> LLMResult: ...

    def stream_chat(self, request: LLMRequest) -> Iterable[str]: ...

    def structured_output(
        self, request: LLMRequest, schema: type[object]
    ) -> dict[str, Any]: ...

    def embeddings(self, *, model: str, input_text: str) -> list[float]: ...

    def health_check(self) -> dict[str, Any]: ...
