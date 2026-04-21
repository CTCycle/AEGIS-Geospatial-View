from __future__ import annotations

from collections.abc import Iterable
from typing import Any

try:
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
except ModuleNotFoundError:  # pragma: no cover - optional dependency in local/dev shells
    ChatOpenAI = None  # type: ignore[assignment]
    OpenAIEmbeddings = None  # type: ignore[assignment]

from AEGIS.server.services.llm.base import LLMProvider
from AEGIS.server.services.llm.cloud_catalog import get_cloud_model_catalog
from AEGIS.server.services.llm.langchain_runtime import (
    invoke_chat_model,
    invoke_structured_chat_model,
    stream_chat_model,
)
from AEGIS.server.services.llm.types import (
    ChatCompletionRequest,
    ChatCompletionResult,
    ModelDescriptor,
)


class OpenAIProvider(LLMProvider):
    provider_name = "openai"

    def __init__(self, *, api_key: str, base_url: str | None = None) -> None:
        self.api_key = api_key
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")

    def _ensure_dependency(self) -> None:
        if ChatOpenAI is None or OpenAIEmbeddings is None:
            raise RuntimeError(
                "langchain_openai is not installed. Install optional LLM dependencies to use OpenAI provider."
            )

    def _build_chat_model(self, *, model: str, temperature: float) -> ChatOpenAI:
        self._ensure_dependency()
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=self.api_key,
            base_url=self.base_url,
        )

    def _build_embedding_model(self, *, model: str) -> OpenAIEmbeddings:
        self._ensure_dependency()
        return OpenAIEmbeddings(
            model=model,
            api_key=self.api_key,
            base_url=self.base_url,
        )

    def list_models(self) -> list[ModelDescriptor]:
        return [
            entry for entry in get_cloud_model_catalog() if entry.provider == "openai"
        ]

    def chat(self, request: ChatCompletionRequest) -> ChatCompletionResult:
        return invoke_chat_model(
            chat_model=self._build_chat_model(
                model=request.model, temperature=request.temperature
            ),
            request=request,
        )

    def stream_chat(self, request: ChatCompletionRequest) -> Iterable[str]:
        return stream_chat_model(
            chat_model=self._build_chat_model(
                model=request.model, temperature=request.temperature
            ),
            request=request,
        )

    def structured_output(
        self, request: ChatCompletionRequest, schema: type[object]
    ) -> dict[str, Any]:
        payload = invoke_structured_chat_model(
            chat_model=self._build_chat_model(
                model=request.model, temperature=request.temperature
            ),
            request=request,
            schema=schema,
        )
        return dict(payload)

    def embeddings(self, *, model: str, input_text: str) -> list[float]:
        values = self._build_embedding_model(model=model).embed_query(input_text)
        if not isinstance(values, list):
            return []
        return [float(value) for value in values if isinstance(value, (int, float))]

    def health_check(self) -> dict[str, Any]:
        return {"ok": True, "detail": "configured"}
