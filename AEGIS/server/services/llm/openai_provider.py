from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from openai import OpenAI

from AEGIS.server.services.llm.base import LLMProvider
from AEGIS.server.services.llm.cloud_catalog import get_cloud_model_catalog
from AEGIS.server.services.llm.response_serialization import dump_response_payload
from AEGIS.server.services.llm.types import LLMRequest, LLMResult, ModelDescriptor


class OpenAIProvider(LLMProvider):
    provider_name = "openai"

    def __init__(self, *, api_key: str, base_url: str | None = None) -> None:
        self.api_key = api_key
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")

    def _client(self) -> Any:
        return OpenAI(api_key=self.api_key, base_url=self.base_url)

    def list_models(self) -> list[ModelDescriptor]:
        return [
            entry for entry in get_cloud_model_catalog() if entry.provider == "openai"
        ]

    def chat(self, request: LLMRequest) -> LLMResult:
        response = self._client().responses.create(
            model=request.model,
            input=request.messages,
            temperature=request.temperature,
        )
        return LLMResult(
            content=str(getattr(response, "output_text", "") or ""),
            raw=dump_response_payload(response),
        )

    def stream_chat(self, request: LLMRequest) -> Iterable[str]:
        stream = self._client().responses.create(
            model=request.model,
            input=request.messages,
            temperature=request.temperature,
            stream=True,
        )
        for event in stream:
            if getattr(event, "type", None) != "response.output_text.delta":
                continue
            delta = getattr(event, "delta", "")
            if delta:
                yield str(delta)

    def structured_output(
        self, request: LLMRequest, schema: type[object]
    ) -> dict[str, Any]:
        response = self._client().responses.parse(
            model=request.model,
            input=request.messages,
            temperature=request.temperature,
            text_format=schema,
        )
        parsed = getattr(response, "output_parsed", None)
        if isinstance(parsed, dict):
            return parsed
        model_dump = getattr(parsed, "model_dump", None)
        if callable(model_dump):
            dumped = model_dump(mode="json")
            return dumped if isinstance(dumped, dict) else {}
        output_text = str(getattr(response, "output_text", "") or "")
        if output_text:
            loaded = json.loads(output_text)
            return loaded if isinstance(loaded, dict) else {}
        return {}

    def embeddings(self, *, model: str, input_text: str) -> list[float]:
        response = self._client().embeddings.create(model=model, input=input_text)
        data = getattr(response, "data", None)
        if not data:
            return []
        embedding = getattr(data[0], "embedding", None)
        if not isinstance(embedding, list):
            return []
        return [float(value) for value in embedding if isinstance(value, (int, float))]

    def health_check(self) -> dict[str, Any]:
        return {"ok": True, "detail": "configured"}

