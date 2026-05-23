from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from typing import Any

from openai import OpenAI

from server.services.llm.base import LLMProvider
from server.services.llm.cloud_catalog import get_cloud_model_catalog
from server.services.llm.context_budget import compute_context_usage
from server.services.llm.response_serialization import dump_response_payload
from server.services.llm.types import LLMRequest, LLMResult, LLMToolCall, LLMToolDefinition, ModelDescriptor


class OpenAIProvider(LLMProvider):
    provider_name = "openai"

    def __init__(self, *, api_key: str, base_url: str | None = None) -> None:
        self.api_key = api_key
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self.last_context_usage: dict[str, Any] | None = None

    def _client(self) -> Any:
        return OpenAI(api_key=self.api_key, base_url=self.base_url)

    def list_models(self) -> list[ModelDescriptor]:
        return [
            entry for entry in get_cloud_model_catalog() if entry.provider == "openai"
        ]

    @staticmethod
    def tool_to_openai_schema(tool: LLMToolDefinition) -> dict[str, Any]:
        return {
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters_json_schema,
        }

    @staticmethod
    def _parse_tool_calls(raw: dict[str, Any]) -> list[LLMToolCall]:
        calls: list[LLMToolCall] = []
        for item in raw.get("output", []) if isinstance(raw.get("output"), list) else []:
            if not isinstance(item, dict) or item.get("type") != "function_call":
                continue
            args = item.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            calls.append(
                LLMToolCall(
                    id=item.get("call_id") or item.get("id"),
                    name=str(item.get("name") or ""),
                    arguments=args if isinstance(args, dict) else {},
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
        self.last_context_usage = compute_context_usage(
            request, provider=self.provider_name
        ).to_dict()
        selected_tools = list(tools or request.tools or [])
        kwargs: dict[str, Any] = {}
        if selected_tools:
            kwargs["tools"] = [self.tool_to_openai_schema(tool) for tool in selected_tools]
            kwargs["tool_choice"] = tool_choice or request.tool_choice or "auto"
        schema = response_json_schema or request.response_json_schema
        if schema:
            kwargs["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "agent_response",
                    "schema": schema,
                    "strict": True,
                }
            }
        response = self._client().responses.create(
            model=request.model,
            input=request.messages,
            temperature=request.temperature,
            **kwargs,
        )
        raw = dump_response_payload(response)
        return LLMResult(
            content=str(getattr(response, "output_text", "") or ""),
            raw=raw,
            tool_calls=self._parse_tool_calls(raw),
        )

    def stream_chat(self, request: LLMRequest) -> Iterable[str]:
        self.last_context_usage = compute_context_usage(
            request, provider=self.provider_name
        ).to_dict()
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
        self.last_context_usage = compute_context_usage(
            request, provider=self.provider_name
        ).to_dict()
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

