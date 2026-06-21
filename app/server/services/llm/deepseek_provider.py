from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import replace
from typing import Any

import httpx
from openai import OpenAI

from server.services.llm.base import LLMProvider
from server.services.llm.context_budget import compute_context_usage
from server.services.llm.types import (
    LLMRequest,
    LLMResult,
    LLMToolCall,
    LLMToolDefinition,
    ModelDescriptor,
)

DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"


###############################################################################
class DeepSeekProvider(LLMProvider):
    provider_name = "deepseek"

    # -------------------------------------------------------------------------
    def __init__(self, *, api_key: str, base_url: str | None = None) -> None:
        self.api_key = api_key
        self.base_url = (base_url or DEFAULT_DEEPSEEK_BASE_URL).rstrip("/")
        self.last_context_usage: dict[str, Any] | None = None

    # -------------------------------------------------------------------------
    def _client(self) -> Any:
        return OpenAI(api_key=self.api_key, base_url=self.base_url)

    # -------------------------------------------------------------------------
    def list_models(self) -> list[ModelDescriptor]:
        response = httpx.get(
            f"{self.base_url}/models",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
            },
            timeout=20.0,
        )
        response.raise_for_status()
        payload = response.json()
        entries = payload.get("data", []) if isinstance(payload, dict) else []
        return [
            self._model_descriptor(item)
            for item in entries
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        ]

    # -------------------------------------------------------------------------
    def supports_tools(self, model: str) -> bool:
        return "tools" in self._capabilities_for_model(model)

    # -------------------------------------------------------------------------
    def supports_structured_output(self, model: str) -> bool:
        capabilities = self._capabilities_for_model(model)
        return "structured" in capabilities or "structured_output" in capabilities

    # -------------------------------------------------------------------------
    def _capabilities_for_model(self, model: str) -> set[str]:
        normalized = model.strip().lower()
        if normalized.startswith("deepseek-"):
            return {"chat", "stream", "structured", "structured_output", "tools"}
        return {"chat", "stream"}

    # -------------------------------------------------------------------------
    @staticmethod
    def tool_to_openai_schema(tool: LLMToolDefinition) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters_json_schema,
            },
        }

    # -------------------------------------------------------------------------
    def chat(
        self,
        request: LLMRequest,
        *,
        tools: Sequence[LLMToolDefinition] | None = None,
        tool_choice: str | None = "auto",
        response_json_schema: dict[str, Any] | None = None,
    ) -> LLMResult:
        self.last_context_usage = compute_context_usage(
            request, provider=self.provider_name
        ).to_dict()
        native_tools = list(tools or request.tools or [])
        schema = response_json_schema or request.response_json_schema
        effective_request = replace(
            request,
            tools=native_tools or None,
            response_json_schema=schema,
        )
        self._validate_request_capabilities(effective_request)
        kwargs: dict[str, Any] = {}
        if native_tools:
            kwargs["tools"] = [
                self.tool_to_openai_schema(tool) for tool in native_tools
            ]
            kwargs["tool_choice"] = tool_choice or request.tool_choice or "auto"
        if schema and not native_tools:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "agent_response",
                    "schema": schema,
                },
            }
        response = self._client().chat.completions.create(
            model=request.model,
            messages=self.normalize_tool_messages(request.messages),
            temperature=request.temperature,
            **kwargs,
        )
        content, tool_calls = self._parse_choice(response)
        return LLMResult(
            content=content,
            raw=response.model_dump(mode="json"),
            tool_calls=tool_calls,
            finish_reason=self._finish_reason(response),
        )

    # -------------------------------------------------------------------------
    def stream_chat(self, request: LLMRequest) -> Iterable[str]:
        self.last_context_usage = compute_context_usage(
            request, provider=self.provider_name
        ).to_dict()
        stream = self._client().chat.completions.create(
            model=request.model,
            messages=self.normalize_tool_messages(request.messages),
            temperature=request.temperature,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta if getattr(chunk, "choices", None) else None
            text = getattr(delta, "content", None)
            if isinstance(text, str) and text:
                yield text

    # -------------------------------------------------------------------------
    def structured_output(
        self, request: LLMRequest, schema: type[object]
    ) -> dict[str, Any]:
        self.last_context_usage = compute_context_usage(
            request, provider=self.provider_name
        ).to_dict()
        json_schema = (
            schema.model_json_schema() if hasattr(schema, "model_json_schema") else {}
        )
        self._validate_request_capabilities(
            replace(request, response_json_schema=json_schema)
        )
        response = self._client().chat.completions.create(
            model=request.model,
            messages=self.normalize_tool_messages(request.messages),
            temperature=request.temperature,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_response",
                    "schema": json_schema,
                },
            },
        )
        content, _ = self._parse_choice(response)
        loaded = json.loads(content or "{}")
        return loaded if isinstance(loaded, dict) else {}

    # -------------------------------------------------------------------------
    def embeddings(self, *, model: str, input_text: str) -> list[float]:
        _ = (model, input_text)
        return []

    # -------------------------------------------------------------------------
    def health_check(self) -> dict[str, Any]:
        return {"ok": True, "detail": "configured"}

    # -------------------------------------------------------------------------
    def normalize_tool_messages(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for message in messages:
            role = str(message.get("role") or "")
            if role == "assistant" and isinstance(message.get("tool_calls"), list):
                normalized.append(
                    {
                        "role": "assistant",
                        "content": message.get("content"),
                        "tool_calls": [
                            {
                                "id": call.get("id"),
                                "type": "function",
                                "function": {
                                    "name": call.get("name"),
                                    "arguments": json.dumps(
                                        call.get("arguments") or {}
                                    ),
                                },
                            }
                            for call in message["tool_calls"]
                            if isinstance(call, dict)
                        ],
                    }
                )
                continue
            if role == "tool":
                normalized.append(
                    {
                        "role": "tool",
                        "tool_call_id": message.get("tool_call_id"),
                        "content": str(message.get("content") or ""),
                    }
                )
                continue
            normalized.append(message)
        return normalized

    # -------------------------------------------------------------------------
    def _model_descriptor(self, item: dict[str, Any]) -> ModelDescriptor:
        model_id = str(item.get("id") or "").strip()
        return ModelDescriptor(
            name=model_id,
            description=self._description_for_model(model_id),
            provider="deepseek",
            capabilities=sorted(self._capabilities_for_model(model_id)),
            metadata={
                "family": model_id.split("-")[0] if "-" in model_id else model_id,
                "owned_by": str(item.get("owned_by") or "deepseek"),
                "tool_support_source": "provider",
            },
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _description_for_model(model_id: str) -> str:
        normalized = model_id.lower()
        if "pro" in normalized:
            return "DeepSeek reasoning model for complex planning, coding, and tool-driven workflows."
        if "flash" in normalized:
            return "Fast DeepSeek model for responsive chat, extraction, and agent tasks."
        if "reasoner" in normalized:
            return "DeepSeek reasoning model compatible with structured outputs and native tool use."
        if "chat" in normalized:
            return "General-purpose DeepSeek chat model."
        return "DeepSeek model discovered from the configured provider account."

    # -------------------------------------------------------------------------
    def _parse_choice(self, response: Any) -> tuple[str, list[LLMToolCall]]:
        choices = getattr(response, "choices", None) or []
        if not choices:
            return "", []
        message = getattr(choices[0], "message", None)
        if message is None:
            return "", []
        content = getattr(message, "content", None)
        text = content if isinstance(content, str) else ""
        raw_tool_calls = getattr(message, "tool_calls", None) or []
        tool_calls: list[LLMToolCall] = []
        for call in raw_tool_calls:
            function = getattr(call, "function", None)
            arguments = getattr(function, "arguments", None)
            parsed_arguments: dict[str, Any] = {}
            if isinstance(arguments, str):
                try:
                    loaded = json.loads(arguments)
                    if isinstance(loaded, dict):
                        parsed_arguments = loaded
                except json.JSONDecodeError:
                    parsed_arguments = {}
            tool_calls.append(
                LLMToolCall(
                    id=getattr(call, "id", None),
                    name=str(getattr(function, "name", "") or ""),
                    arguments=parsed_arguments,
                )
            )
        return text, tool_calls

    # -------------------------------------------------------------------------
    @staticmethod
    def _finish_reason(response: Any) -> str | None:
        choices = getattr(response, "choices", None) or []
        if not choices:
            return None
        finish_reason = getattr(choices[0], "finish_reason", None)
        return str(finish_reason) if finish_reason else None
