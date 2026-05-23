from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from typing import Any

from google import genai
from google.genai import types as genai_types

from server.services.llm.base import LLMProvider
from server.services.llm.cloud_catalog import get_cloud_model_catalog
from server.services.llm.context_budget import compute_context_usage
from server.services.llm.response_serialization import dump_response_payload
from server.services.llm.types import LLMRequest, LLMResult, LLMToolCall, LLMToolDefinition, ModelDescriptor

DEFAULT_GOOGLE_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GoogleProvider(LLMProvider):
    provider_name = "google"

    def __init__(self, *, api_key: str, base_url: str | None = None) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/") if base_url else None
        self.last_context_usage: dict[str, Any] | None = None

    def _client(self) -> Any:
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

    @staticmethod
    def tool_to_google_schema(tool: LLMToolDefinition) -> dict[str, Any]:
        return {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters_json_schema,
        }

    @staticmethod
    def _parse_tool_calls(raw: dict[str, Any]) -> list[LLMToolCall]:
        calls: list[LLMToolCall] = []
        candidates = raw.get("candidates") if isinstance(raw, dict) else None
        for candidate in candidates if isinstance(candidates, list) else []:
            content = candidate.get("content") if isinstance(candidate, dict) else {}
            for part in content.get("parts", []) if isinstance(content, dict) else []:
                function_call = part.get("functionCall") or part.get("function_call") if isinstance(part, dict) else None
                if not isinstance(function_call, dict):
                    continue
                args = function_call.get("args") or {}
                calls.append(
                    LLMToolCall(
                        id=function_call.get("id"),
                        name=str(function_call.get("name") or ""),
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
        config = self._config_from_request(request)
        selected_tools = list(tools or request.tools or [])
        if selected_tools:
            config["tools"] = [
                {"function_declarations": [self.tool_to_google_schema(tool) for tool in selected_tools]}
            ]
            config["tool_config"] = {"function_calling_config": {"mode": "AUTO" if (tool_choice or request.tool_choice) != "none" else "NONE"}}
        schema = response_json_schema or request.response_json_schema
        if schema:
            config["response_mime_type"] = "application/json"
            config["response_json_schema"] = schema
        response = self._client().models.generate_content(
            model=request.model,
            contents=self._contents_from_messages(request.messages),
            config=config,
        )
        raw = dump_response_payload(response)
        return LLMResult(
            content=str(getattr(response, "text", "") or ""),
            raw=raw,
            tool_calls=self._parse_tool_calls(raw),
        )

    def stream_chat(self, request: LLMRequest) -> Iterable[str]:
        self.last_context_usage = compute_context_usage(
            request, provider=self.provider_name
        ).to_dict()
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
        self.last_context_usage = compute_context_usage(
            request, provider=self.provider_name
        ).to_dict()
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

