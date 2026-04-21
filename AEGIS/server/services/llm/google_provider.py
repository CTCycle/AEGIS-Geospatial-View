from __future__ import annotations

from collections.abc import Iterable
from typing import Any

try:
    from langchain_google_genai import (
        ChatGoogleGenerativeAI,
        GoogleGenerativeAIEmbeddings,
    )
except ModuleNotFoundError:  # pragma: no cover - optional dependency in local/dev shells
    ChatGoogleGenerativeAI = None  # type: ignore[assignment]
    GoogleGenerativeAIEmbeddings = None  # type: ignore[assignment]

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


class GoogleProvider(LLMProvider):
    provider_name = "google"

    def __init__(self, *, api_key: str, base_url: str | None = None) -> None:
        self.api_key = api_key
        self.base_url = (
            base_url or "https://generativelanguage.googleapis.com/v1beta"
        ).rstrip("/")

    def _ensure_dependency(self) -> None:
        if ChatGoogleGenerativeAI is None or GoogleGenerativeAIEmbeddings is None:
            raise RuntimeError(
                "langchain_google_genai is not installed. Install optional LLM dependencies to use Google provider."
            )

    def _build_chat_model(
        self, *, model: str, temperature: float
    ) -> ChatGoogleGenerativeAI:
        self._ensure_dependency()
        kwargs: dict[str, Any] = {
            "model": model,
            "temperature": temperature,
            "google_api_key": self.api_key,
        }
        if self.base_url:
            kwargs["api_endpoint"] = self.base_url
        try:
            return ChatGoogleGenerativeAI(**kwargs)
        except TypeError:
            kwargs.pop("api_endpoint", None)
            return ChatGoogleGenerativeAI(**kwargs)

    def _build_embedding_model(
        self, *, model: str
    ) -> GoogleGenerativeAIEmbeddings:
        self._ensure_dependency()
        kwargs: dict[str, Any] = {
            "model": model,
            "google_api_key": self.api_key,
        }
        if self.base_url:
            kwargs["api_endpoint"] = self.base_url
        try:
            return GoogleGenerativeAIEmbeddings(**kwargs)
        except TypeError:
            kwargs.pop("api_endpoint", None)
            return GoogleGenerativeAIEmbeddings(**kwargs)

    def list_models(self) -> list[ModelDescriptor]:
        return [
            entry for entry in get_cloud_model_catalog() if entry.provider == "google"
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
