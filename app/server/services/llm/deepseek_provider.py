from __future__ import annotations

from server.common.typing import is_json_array, is_json_object, json_array, json_object

import json
from collections.abc import Iterable, Sequence
from dataclasses import replace
from typing import Any

import httpx
from openai import OpenAI

from server.services.llm.base import LLMProvider
from server.services.llm.context_budget import compute_context_usage, prepare_request
from server.prompts.providers import build_deepseek_json_schema_instruction
from server.services.llm.errors import (
    LLMProviderRequestError,
    LLMResponseParsingError,
)
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
        self._declared_model_capabilities: dict[str, dict[str, bool]] = {}

    # -------------------------------------------------------------------------
    def _client(self) -> Any:
        return OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=30.0,
            max_retries=0,
        )

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
        entries = json_array(json_object(payload).get("data"))
        models = [
            self._model_descriptor(item)
            for item in entries
            if is_json_object(item) and str(item.get("id") or "").strip()
        ]
        for model in models:
            declared = {
                key: value
                for key, value in model.metadata.items()
                if key in {"supports_tools", "supports_structured_output"}
                and isinstance(value, bool)
            }
            if declared:
                self._declared_model_capabilities[model.name] = declared
        return models

    # -------------------------------------------------------------------------
    def supports_tools(self, model: str) -> bool | None:
        declared = self._declared_model_capabilities.get(model, {}).get("supports_tools")
        if isinstance(declared, bool):
            return declared
        return True if model.strip().lower().startswith("deepseek-") else None

    # -------------------------------------------------------------------------
    def supports_structured_output(self, model: str) -> bool | None:
        declared = self._declared_model_capabilities.get(model, {}).get("supports_structured_output")
        if isinstance(declared, bool):
            return declared
        return True if model.strip().lower().startswith("deepseek-") else None

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
        request = prepare_request(request, provider=self.provider_name)
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
            kwargs["response_format"] = {"type": "json_object"}
            effective_request = replace(
                effective_request,
                messages=self._messages_with_json_schema(
                    effective_request.messages, schema
                ),
            )
        try:
            response = self._client().chat.completions.create(
                model=request.model,
                messages=self.normalize_tool_messages(effective_request.messages),
                temperature=request.temperature,
                **kwargs,
            )
        except Exception as exc:
            raise LLMProviderRequestError.from_exception(
                exc, provider=self.provider_name, model=request.model, stage="chat"
            ) from exc
        content, tool_calls = self._parse_choice(response)
        return LLMResult(
            content=content,
            raw=response.model_dump(mode="json"),
            tool_calls=tool_calls,
            finish_reason=self._finish_reason(response),
        )

    # -------------------------------------------------------------------------
    def stream_chat(self, request: LLMRequest) -> Iterable[str]:
        request = prepare_request(request, provider=self.provider_name)
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
        self, request: LLMRequest, schema: type[Any]
    ) -> dict[str, Any]:
        request = prepare_request(request, provider=self.provider_name)
        self.last_context_usage = compute_context_usage(
            request, provider=self.provider_name
        ).to_dict()
        model_json_schema = getattr(schema, "model_json_schema", None)
        json_schema = json_object(model_json_schema()) if callable(model_json_schema) else {}
        self._validate_request_capabilities(
            replace(request, response_json_schema=json_schema)
        )
        try:
            response = self._client().chat.completions.create(
                model=request.model,
                messages=self.normalize_tool_messages(
                    self._messages_with_json_schema(request.messages, json_schema)
                ),
                temperature=request.temperature,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            raise LLMProviderRequestError.from_exception(
                exc, provider=self.provider_name, model=request.model, stage="structured_output"
            ) from exc
        content, _ = self._parse_choice(response)
        try:
            loaded = json.loads(content or "{}")
        except (TypeError, json.JSONDecodeError) as exc:
            raise LLMResponseParsingError(
                provider=self.provider_name,
                model=request.model,
                stage="structured_output",
                detail="The provider returned invalid JSON for structured extraction.",
            ) from exc
        if not is_json_object(loaded):
            raise LLMResponseParsingError(
                provider=self.provider_name,
                model=request.model,
                stage="structured_output",
                detail="The provider returned a JSON value instead of an object.",
            )
        validator = getattr(schema, "model_validate", None)
        if not callable(validator):
            return loaded
        try:
            validated = validator(loaded)
        except Exception as exc:  # noqa: BLE001
            raise LLMResponseParsingError(
                provider=self.provider_name,
                model=request.model,
                stage="structured_output",
                detail="The provider response did not match the requested extraction schema.",
            ) from exc
        dumper = getattr(validated, "model_dump", None)
        return json_object(dumper(mode="json")) if callable(dumper) else loaded

    # -------------------------------------------------------------------------
    @staticmethod
    def _messages_with_json_schema(
        messages: list[dict[str, Any]], schema: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return [
            *messages,
            {
                "role": "system",
                "content": build_deepseek_json_schema_instruction(schema),
            },
        ]

    # -------------------------------------------------------------------------
    def embeddings(self, *, model: str, input_text: str) -> list[float]:
        _ = (model, input_text)
        return []

    # -------------------------------------------------------------------------
    def health_check(self) -> dict[str, Any]:
        return {"ok": True, "detail": "configured"}

    # -------------------------------------------------------------------------
    @staticmethod
    def normalize_tool_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for message in messages:
            role = str(message.get("role") or "")
            if role == "assistant" and is_json_array(message.get("tool_calls")):
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
                            if is_json_object(call)
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
        metadata: dict[str, Any] = {
            "family": model_id.split("-")[0] if "-" in model_id else model_id,
            "owned_by": str(item.get("owned_by") or "deepseek"),
            "tool_support_source": "provider",
        }
        for key in (
            "context_window_tokens",
            "context_length",
            "maximum_output_tokens",
            "max_output_tokens",
        ):
            if item.get(key) is not None:
                metadata[key] = item[key]
        raw_capabilities = item.get("capabilities")
        if isinstance(raw_capabilities, list):
            normalized = {
                str(value).strip().lower()
                for value in raw_capabilities
                if str(value).strip()
            }
            metadata["supports_tools"] = "tools" in normalized
            metadata["supports_structured_output"] = bool(
                {"structured", "structured_output"} & normalized
            )
            capabilities = sorted(normalized)
        else:
            capabilities = sorted(self._capabilities_for_model(model_id))
        return ModelDescriptor(
            name=model_id,
            description=self._description_for_model(model_id),
            provider="deepseek",
            capabilities=capabilities,
            metadata=metadata,
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
        choices: list[Any] = list(getattr(response, "choices", None) or [])
        if not choices:
            return "", []
        message = getattr(choices[0], "message", None)
        if message is None:
            return "", []
        content = getattr(message, "content", None)
        text = content if isinstance(content, str) else ""
        raw_tool_calls: list[Any] = list(getattr(message, "tool_calls", None) or [])
        tool_calls: list[LLMToolCall] = []
        for call in raw_tool_calls:
            function = getattr(call, "function", None)
            arguments = getattr(function, "arguments", None)
            parsed_arguments: dict[str, Any] = {}
            if isinstance(arguments, str):
                try:
                    loaded = json.loads(arguments)
                    if is_json_object(loaded):
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
        choices: list[Any] = list(getattr(response, "choices", None) or [])
        if not choices:
            return None
        finish_reason = getattr(choices[0], "finish_reason", None)
        return str(finish_reason) if finish_reason else None
