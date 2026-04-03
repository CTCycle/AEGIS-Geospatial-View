from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any
from urllib.request import Request, urlopen

from AEGIS.server.services.llm.base import LLMProvider
from AEGIS.server.services.llm.cloud_catalog import get_cloud_model_catalog
from AEGIS.server.services.llm.types import ChatCompletionRequest, ChatCompletionResult, ModelDescriptor


class GoogleProvider(LLMProvider):
    provider_name = "google"

    def __init__(self, *, api_key: str, base_url: str | None = None) -> None:
        self.api_key = api_key
        self.base_url = (
            base_url or "https://generativelanguage.googleapis.com/v1beta"
        ).rstrip("/")

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            f"{self.base_url}{path}?key={self.api_key}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8"))

    def list_models(self) -> list[ModelDescriptor]:
        return [entry for entry in get_cloud_model_catalog() if entry.provider == "google"]

    def chat(self, request: ChatCompletionRequest) -> ChatCompletionResult:
        text = "\n".join(item.get("content", "") for item in request.messages)
        payload = self._post_json(
            f"/models/{request.model}:generateContent",
            {"contents": [{"parts": [{"text": text}]}]},
        )
        candidates = payload.get("candidates", [])
        content = ""
        if isinstance(candidates, list) and candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if isinstance(parts, list) and parts:
                content = str(parts[0].get("text") or "")
        return ChatCompletionResult(content=content, raw=payload)

    def stream_chat(self, request: ChatCompletionRequest) -> Iterable[str]:
        yield self.chat(request).content

    def structured_output(self, request: ChatCompletionRequest, schema: dict[str, Any]) -> dict[str, Any]:
        result = self.chat(request)
        try:
            parsed = json.loads(result.content)
        except json.JSONDecodeError:
            parsed = {}
        return parsed if isinstance(parsed, dict) else {}

    def embeddings(self, *, model: str, input_text: str) -> list[float]:
        payload = self._post_json(
            f"/models/{model}:embedContent",
            {"content": {"parts": [{"text": input_text}]}},
        )
        values = payload.get("embedding", {}).get("values", [])
        if not isinstance(values, list):
            return []
        return [float(value) for value in values if isinstance(value, (int, float))]

    def health_check(self) -> dict[str, Any]:
        return {"ok": True, "detail": "configured"}
