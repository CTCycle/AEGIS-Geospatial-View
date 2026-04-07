from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from AEGIS.server.services.llm.base import LLMProvider
from AEGIS.server.services.llm.cloud_catalog import get_cloud_model_catalog
from AEGIS.server.services.llm.types import ChatCompletionRequest, ChatCompletionResult, ModelDescriptor


class OpenAIProvider(LLMProvider):
    provider_name = "openai"

    def __init__(self, *, api_key: str, base_url: str | None = None) -> None:
        self.api_key = api_key
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=45) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace").strip()
            message = f"OpenAI request failed with HTTP {exc.code}"
            if detail:
                message = f"{message}: {detail}"
            raise ValueError(message) from exc
        except URLError as exc:
            raise ValueError(f"OpenAI request failed: {exc.reason}") from exc

    def list_models(self) -> list[ModelDescriptor]:
        return [entry for entry in get_cloud_model_catalog() if entry.provider == "openai"]

    def chat(self, request: ChatCompletionRequest) -> ChatCompletionResult:
        payload = self._post_json(
            "/chat/completions",
            {
                "model": request.model,
                "messages": request.messages,
                "temperature": request.temperature,
            },
        )
        choices = payload.get("choices", [])
        content = ""
        if isinstance(choices, list) and choices:
            message = choices[0].get("message", {})
            if isinstance(message, dict):
                content = str(message.get("content") or "")
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
        payload = self._post_json("/embeddings", {"model": model, "input": input_text})
        data = payload.get("data", [])
        if not isinstance(data, list) or not data:
            return []
        embedding = data[0].get("embedding", [])
        if not isinstance(embedding, list):
            return []
        return [float(value) for value in embedding if isinstance(value, (int, float))]

    def health_check(self) -> dict[str, Any]:
        return {"ok": True, "detail": "configured"}
