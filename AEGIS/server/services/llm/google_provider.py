from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

try:
    from google import genai
    from google.genai import types as genai_types
except ModuleNotFoundError:  # pragma: no cover - optional dependency in local/dev shells
    genai = None  # type: ignore[assignment]
    genai_types = None  # type: ignore[assignment]

from AEGIS.server.services.llm.base import LLMProvider
from AEGIS.server.services.llm.cloud_catalog import get_cloud_model_catalog
from AEGIS.server.services.llm.types import LLMRequest, LLMResult, ModelDescriptor

DEFAULT_GOOGLE_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GoogleProvider(LLMProvider):
    provider_name = "google"

    def __init__(self, *, api_key: str, base_url: str | None = None) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/") if base_url else None

    def _ensure_dependency(self) -> None:
        if genai is None or genai_types is None:
            raise RuntimeError(
                "google-genai is not installed. Install LLM dependencies to use Google provider."
            )

    def _client(self) -> Any:
        self._ensure_dependency()
        if self.base_url and self.base_url != DEFAULT_GOOGLE_BASE_URL:
            return genai.Client(
                api_key=self.api_key,
                http_options=genai_types.HttpOptions(
                    baseUrl=self.base_url,
                    apiVersion="v1beta",
                ),
            )
        return genai.Client(api_key=self.api_key)

    def list_models(self) -> list[ModelDescriptor]:
        return [
            entry for entry in get_cloud_model_catalog() if entry.provider == "google"
        ]

    def chat(self, request: LLMRequest) -> LLMResult:
        response = self._client().models.generate_content(
            model=request.model,
            contents=self._contents_from_messages(request.messages),
            config=self._config_from_request(request),
        )
        return LLMResult(
            content=str(getattr(response, "text", "") or ""),
            raw=self._dump_response(response),
        )

    def stream_chat(self, request: LLMRequest) -> Iterable[str]:
        stream = self._client().models.generate_content_stream(
            model=request.model,
            contents=self._contents_from_messages(request.messages),
            config=self._config_from_request(request),
        )
        for chunk in stream:
            text = getattr(chunk, "text", "")
            if text:
                yield str(text)

    def structured_output(
        self, request: LLMRequest, schema: type[object]
    ) -> dict[str, Any]:
        schema_dump = getattr(schema, "model_json_schema", None)
        json_schema = schema_dump() if callable(schema_dump) else {}
        response = self._client().models.generate_content(
            model=request.model,
            contents=self._contents_from_messages(request.messages),
            config={
                **self._config_from_request(request),
                "response_mime_type": "application/json",
                "response_json_schema": json_schema,
            },
        )
        loaded = json.loads(str(getattr(response, "text", "") or "{}"))
        return loaded if isinstance(loaded, dict) else {}

    def embeddings(self, *, model: str, input_text: str) -> list[float]:
        response = self._client().models.embed_content(model=model, contents=input_text)
        embeddings = getattr(response, "embeddings", None)
        if embeddings:
            values = getattr(embeddings[0], "values", None)
            if isinstance(values, list):
                return [
                    float(value) for value in values if isinstance(value, (int, float))
                ]
        embedding = getattr(response, "embedding", None)
        values = getattr(embedding, "values", None)
        if isinstance(values, list):
            return [float(value) for value in values if isinstance(value, (int, float))]
        return []

    def health_check(self) -> dict[str, Any]:
        return {"ok": True, "detail": "configured"}

    @staticmethod
    def _contents_from_messages(messages: list[dict[str, str]]) -> list[dict[str, Any]]:
        contents: list[dict[str, Any]] = []
        for message in messages:
            role = str(message.get("role") or "").strip().lower()
            if role == "system":
                continue
            mapped_role = "model" if role == "assistant" else "user"
            contents.append(
                {
                    "role": mapped_role,
                    "parts": [{"text": str(message.get("content") or "")}],
                }
            )
        return contents or [{"role": "user", "parts": [{"text": ""}]}]

    @staticmethod
    def _config_from_request(request: LLMRequest) -> dict[str, Any]:
        system_instruction = "\n\n".join(
            str(message.get("content") or "")
            for message in request.messages
            if str(message.get("role") or "").strip().lower() == "system"
        )
        config: dict[str, Any] = {"temperature": request.temperature}
        if system_instruction:
            config["system_instruction"] = system_instruction
        return config

    @staticmethod
    def _dump_response(response: object) -> dict[str, Any]:
        model_dump = getattr(response, "model_dump", None)
        if callable(model_dump):
            dumped = model_dump(mode="json")
            return dumped if isinstance(dumped, dict) else {}
        if isinstance(response, dict):
            return response
        return {}
