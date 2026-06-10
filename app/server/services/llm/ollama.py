from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import replace
from html.parser import HTMLParser
from typing import Any, TextIO
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from server.services.llm.base import LLMProvider
from server.services.llm.context_budget import compute_ollama_context_usage
from server.services.llm.ollama_capability_cache import OllamaToolCapabilityCache
from server.services.llm.types import (
    LLMRequest,
    LLMResult,
    LLMToolCall,
    LLMToolDefinition,
    ModelDescriptor,
)


class _OllamaLibraryParser(HTMLParser):
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
            normalized = normalized[len(self._active_model) :].strip(" -:•")
        self.entries[self._active_model] = (
            normalized or f"Ollama library model {self._active_model}"
        )
        self._active_model = None
        self._chunks = []


class OllamaProvider(LLMProvider):
    provider_name = "ollama"

    def __init__(
        self,
        *,
        base_url: str,
        tool_capability_cache: OllamaToolCapabilityCache | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.tool_capability_cache = tool_capability_cache or OllamaToolCapabilityCache()
        self.last_context_usage: dict[str, Any] | None = None

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def _stream_post(
        self, path: str, payload: dict[str, Any]
    ) -> Iterator[dict[str, Any]]:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=60) as response:
            reader: TextIO = response  # type: ignore[assignment]
            for line in reader:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    pass

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
            details = (
                item.get("details") if isinstance(item.get("details"), dict) else {}
            )
            family = str(details.get("family") or "").strip()
            parameter_size = str(details.get("parameter_size") or "").strip()
            quantization_level = str(details.get("quantization_level") or "").strip()
            details_chunks = [
                chunk for chunk in [family, parameter_size, quantization_level] if chunk
            ]
            description = (
                " | ".join(details_chunks)
                if details_chunks
                else f"Local Ollama model {model_name}"
            )
            models.append(
                self._descriptor_from_tag_item(
                    item=item,
                    model_name=model_name,
                    description=description,
                    family=family,
                    parameter_size=parameter_size,
                    quantization_level=quantization_level,
                )
            )
        return models

    def _descriptor_from_tag_item(
        self,
        *,
        item: dict[str, Any],
        model_name: str,
        description: str,
        family: str,
        parameter_size: str,
        quantization_level: str,
    ) -> ModelDescriptor:
        capabilities = self.get_model_capabilities(model_name)
        supports_tools = "tools" in capabilities
        source = self._tool_support_source(model_name)
        return ModelDescriptor(
            name=model_name,
            description=description,
            provider="ollama",
            capabilities=sorted(capabilities),
            metadata={
                "size": item.get("size"),
                "family": family,
                "parameter_size": parameter_size,
                "quantization_level": quantization_level,
                "supports_tools": supports_tools,
                "tool_support_source": source,
            },
        )

    def get_model_capabilities(self, model: str) -> set[str]:
        capabilities = {"chat", "stream", "embeddings"}
        show_capabilities = self._show_capabilities(model)
        if show_capabilities is not None:
            if "tools" in show_capabilities:
                capabilities.add("tools")
            self.tool_capability_cache.set(
                self.base_url,
                model,
                "tools" in show_capabilities,
                source="ollama_show",
            )
            return capabilities
        if self._probe_tool_support(model):
            capabilities.add("tools")
        return capabilities

    def supports_tools(self, model: str) -> bool:
        return "tools" in self.get_model_capabilities(model)

    def supports_structured_output(self, model: str) -> bool:
        _ = model
        return True

    def _show_capabilities(self, model: str) -> set[str] | None:
        try:
            payload = self._post_json("/api/show", {"name": model})
        except Exception:
            return None
        raw = payload.get("capabilities")
        if not isinstance(raw, list):
            return None
        return {str(item).strip().lower() for item in raw if str(item).strip()}

    def _probe_tool_support(self, model: str) -> bool:
        cached = self.tool_capability_cache.get(self.base_url, model)
        if cached is not None:
            return cached
        tool = LLMToolDefinition(
            name="aegis_tool_probe",
            description="Harmless capability probe.",
            parameters_json_schema={"type": "object", "properties": {}},
        )
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": "Call the aegis_tool_probe tool with empty arguments.",
                }
            ],
            "stream": False,
            "tools": [self.tool_to_ollama_schema(tool)],
            "options": {"temperature": 0},
        }
        supported = False
        try:
            response = self._post_json("/api/chat", payload)
            message = response.get("message") if isinstance(response, dict) else None
            supported = bool(
                isinstance(message, dict) and self._parse_tool_calls(message)
            )
        except Exception:
            supported = False
        self.tool_capability_cache.set(
            self.base_url,
            model,
            supported,
            source="ollama_probe",
        )
        return supported

    def _tool_support_source(self, model: str) -> str:
        return self.tool_capability_cache.source(self.base_url, model) or "unknown"

    def list_library_models(self) -> list[ModelDescriptor]:
        try:
            html = self._get_text("https://registry.ollama.ai/library")
            parser = _OllamaLibraryParser()
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

    @staticmethod
    def tool_to_ollama_schema(tool: LLMToolDefinition) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters_json_schema,
            },
        }

    @staticmethod
    def _parse_tool_calls(message: dict[str, Any]) -> list[LLMToolCall]:
        calls: list[LLMToolCall] = []
        for item in message.get("tool_calls", []) if isinstance(message, dict) else []:
            if not isinstance(item, dict):
                continue
            function = item.get("function") if isinstance(item.get("function"), dict) else {}
            calls.append(
                LLMToolCall(
                    id=item.get("id"),
                    name=str(function.get("name") or item.get("name") or ""),
                    arguments=function.get("arguments") if isinstance(function.get("arguments"), dict) else {},
                )
            )
        return calls

    def chat(
        self,
        request: LLMRequest,
        *,
        tools: Sequence[LLMToolDefinition] | None = None,
        tool_choice: str | None = "auto",
        response_json_schema: dict[str, Any] | None = None,
    ) -> LLMResult:
        usage = compute_ollama_context_usage(request)
        self.last_context_usage = usage.to_dict()
        native_tools = list(tools or request.tools or [])
        schema = response_json_schema or request.response_json_schema
        effective_request = replace(
            request,
            tools=native_tools or None,
            response_json_schema=schema,
        )
        self._validate_request_capabilities(effective_request)
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": request.messages,
            "stream": False,
            "options": {"temperature": request.temperature, "num_ctx": usage.selected_context_window},
        }
        if native_tools:
            payload["tools"] = [self.tool_to_ollama_schema(tool) for tool in native_tools]
        if schema:
            payload["format"] = schema
        response = self._post_json("/api/chat", payload)
        message = response.get("message") if isinstance(response.get("message"), dict) else {}
        return LLMResult(
            content=str(message.get("content") or ""),
            raw=response,
            tool_calls=self._parse_tool_calls(message),
            finish_reason=str(response.get("done_reason") or "") or None,
        )

    def stream_chat(self, request: LLMRequest) -> Iterable[str]:
        usage = compute_ollama_context_usage(request)
        self.last_context_usage = usage.to_dict()
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": request.messages,
            "stream": True,
            "options": {"temperature": request.temperature, "num_ctx": usage.selected_context_window},
        }
        for event in self._stream_post("/api/chat", payload):
            message = event.get("message") if isinstance(event.get("message"), dict) else None
            if message is not None:
                content = message.get("content")
                if isinstance(content, str) and content:
                    yield content
            if event.get("done"):
                break

    def structured_output(
        self, request: LLMRequest, schema: type[object]
    ) -> dict[str, Any]:
        usage = compute_ollama_context_usage(request)
        self.last_context_usage = usage.to_dict()
        schema_json = schema.model_json_schema() if hasattr(schema, "model_json_schema") else {}
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": request.messages,
            "stream": False,
            "format": schema_json,
            "options": {"temperature": request.temperature, "num_ctx": usage.selected_context_window},
        }
        response = self._post_json("/api/chat", payload)
        message = response.get("message") if isinstance(response.get("message"), dict) else {}
        content = str(message.get("content") or "{}")
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {}

    def embeddings(self, *, model: str, input_text: str) -> list[float]:
        payload: dict[str, Any] = {
            "model": model,
            "prompt": input_text,
        }
        try:
            response = self._post_json("/api/embeddings", payload)
        except Exception:
            return []
        embedding = response.get("embedding")
        if not isinstance(embedding, list):
            return []
        return [float(value) for value in embedding if isinstance(value, (int | float))]

    def health_check(self) -> dict[str, Any]:
        try:
            payload = self._get_json("/api/tags")
            return {
                "ok": True,
                "detail": "reachable",
                "models": len(payload.get("models", [])),
            }
        except (HTTPError, URLError, TimeoutError) as exc:
            return {"ok": False, "detail": str(exc)}
