from __future__ import annotations

import json
from html.parser import HTMLParser
from collections.abc import Iterable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from AEGIS.server.services.llm.base import LLMProvider
from AEGIS.server.services.llm.types import ChatCompletionRequest, ChatCompletionResult, ModelDescriptor


class OllamaProvider(LLMProvider):
    provider_name = "ollama"

    def __init__(self, *, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def _get_json(self, path: str) -> dict[str, Any]:
        request = Request(f"{self.base_url}{path}", method="GET")
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    def _get_text(self, url: str) -> str:
        request = Request(url, headers={"User-Agent": "AEGIS/1.0"}, method="GET")
        with urlopen(request, timeout=20) as response:
            return response.read().decode("utf-8", errors="ignore")

    def list_models(self) -> list[ModelDescriptor]:
        try:
            payload = self._get_json("/api/tags")
        except Exception:
            return []
        models: list[ModelDescriptor] = []
        for item in payload.get("models", []):
            if not isinstance(item, dict):
                continue
            model_name = str(item.get("name") or "")
            if not model_name:
                continue
            details = item.get("details") if isinstance(item.get("details"), dict) else {}
            family = str(details.get("family") or "").strip()
            parameter_size = str(details.get("parameter_size") or "").strip()
            quantization_level = str(details.get("quantization_level") or "").strip()
            details_chunks = [chunk for chunk in [family, parameter_size, quantization_level] if chunk]
            description = (
                " | ".join(details_chunks)
                if details_chunks
                else f"Local Ollama model {model_name}"
            )
            models.append(
                ModelDescriptor(
                    name=model_name,
                    description=description,
                    provider="ollama",
                    capabilities=["chat", "stream", "embeddings"],
                    metadata={
                        "size": item.get("size"),
                        "family": family,
                        "parameter_size": parameter_size,
                        "quantization_level": quantization_level,
                    },
                )
            )
        return models

    def list_library_models(self) -> list[ModelDescriptor]:
        class _LibraryParser(HTMLParser):
            def __init__(self) -> None:
                super().__init__()
                self._active_model: str | None = None
                self._chunks: list[str] = []
                self.entries: dict[str, str] = {}

            def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
                if tag != "a":
                    return
                attr_map = {key: value for key, value in attrs}
                href = attr_map.get("href") or ""
                if not href.startswith("/library/"):
                    return
                model = href.removeprefix("/library/").split("/", maxsplit=1)[0].strip()
                if not model or model in self.entries:
                    return
                self._active_model = model
                self._chunks = []

            def handle_data(self, data: str) -> None:
                if self._active_model is None:
                    return
                text = data.strip()
                if text:
                    self._chunks.append(text)

            def handle_endtag(self, tag: str) -> None:
                if tag != "a" or self._active_model is None:
                    return
                merged = " ".join(self._chunks).strip()
                normalized = " ".join(merged.split())
                if normalized.lower().startswith(self._active_model.lower()):
                    normalized = normalized[len(self._active_model):].strip(" -:•")
                self.entries[self._active_model] = normalized or f"Ollama library model {self._active_model}"
                self._active_model = None
                self._chunks = []

        try:
            html = self._get_text("https://registry.ollama.ai/library")
            parser = _LibraryParser()
            parser.feed(html)
        except Exception:
            return []
        return [
            ModelDescriptor(
                name=name,
                description=description,
                provider="ollama",
                capabilities=["chat", "stream", "embeddings"],
                metadata={"source": "ollama-library"},
            )
            for name, description in parser.entries.items()
        ]

    def pull_model(self, *, model: str) -> dict[str, Any]:
        return self._post_json("/api/pull", {"name": model, "stream": False})

    def chat(self, request: ChatCompletionRequest) -> ChatCompletionResult:
        payload = self._post_json(
            "/api/chat",
            {"model": request.model, "messages": request.messages, "stream": False},
        )
        message = payload.get("message", {}) if isinstance(payload, dict) else {}
        content = str(message.get("content") or "")
        return ChatCompletionResult(content=content, raw=payload)

    def stream_chat(self, request: ChatCompletionRequest) -> Iterable[str]:
        payload = self.chat(request)
        if payload.content:
            yield payload.content

    def structured_output(self, request: ChatCompletionRequest, schema: dict[str, Any]) -> dict[str, Any]:
        result = self.chat(request)
        try:
            parsed = json.loads(result.content)
        except json.JSONDecodeError:
            parsed = {}
        if not isinstance(parsed, dict):
            return {}
        return parsed

    def embeddings(self, *, model: str, input_text: str) -> list[float]:
        payload = self._post_json("/api/embeddings", {"model": model, "prompt": input_text})
        vector = payload.get("embedding", [])
        if not isinstance(vector, list):
            return []
        return [float(value) for value in vector if isinstance(value, (int, float))]

    def health_check(self) -> dict[str, Any]:
        try:
            payload = self._get_json("/api/tags")
            return {"ok": True, "detail": "reachable", "models": len(payload.get("models", []))}
        except (HTTPError, URLError, TimeoutError) as exc:
            return {"ok": False, "detail": str(exc)}
