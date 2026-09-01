from __future__ import annotations

from server.common.typing import is_json_array, is_json_object, json_array, json_object

import json
from collections.abc import Iterable, Sequence
from dataclasses import replace
from typing import Any

from openai import OpenAI

from server.services.llm.base import LLMProvider
from server.services.llm.cloud_catalog import get_cloud_model_catalog
from server.services.llm.context_budget import (
    apply_reported_usage,
    compute_context_usage,
    prepare_request,
)
from server.services.llm.errors import (
    LLMProviderRequestError,
    LLMResponseParsingError,
    LLMStructuredOutputError,
)
from server.services.llm.response_serialization import dump_response_payload
from server.services.llm.request_deadline import remaining_request_seconds
from server.services.llm.types import (
    LLMRequest,
    LLMResult,
    LLMStructuredOutput,
    LLMTextStream,
    LLMToolCall,
    LLMToolDefinition,
    ModelDescriptor,
)


###############################################################################
class OpenAIProvider(LLMProvider):
    provider_name = "openai"

    # -------------------------------------------------------------------------
    def __init__(self, *, api_key: str, base_url: str | None = None) -> None:
        self.api_key = api_key
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")

    # -------------------------------------------------------------------------
    def _client(self) -> Any:
        return OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=30.0,
            max_retries=0,
        )

    # -------------------------------------------------------------------------
    def _client_for_request(self, request: LLMRequest) -> Any:
        client = self._client()
        remaining = remaining_request_seconds(request)
        if remaining is None:
            return client
        if remaining <= 0:
            raise TimeoutError("The bounded LLM request deadline has expired.")
        with_options = getattr(client, "with_options", None)
        if callable(with_options):
            return with_options(timeout=min(30.0, remaining))
        return client

    # -------------------------------------------------------------------------
    def list_models(self) -> list[ModelDescriptor]:
        return [
            entry for entry in get_cloud_model_catalog() if entry.provider == "openai"
        ]

    # -------------------------------------------------------------------------
    def supports_tools(self, model: str) -> bool | None:
        for entry in self.list_models():
            if entry.name == model:
                return "tools" in entry.capabilities
        return None

    # -------------------------------------------------------------------------
    def supports_structured_output(self, model: str) -> bool | None:
        for entry in self.list_models():
            if entry.name == model:
                return bool(
                    {"structured", "structured_output"} & set(entry.capabilities)
                )
        return None

    # -------------------------------------------------------------------------
    def _capabilities_for_model(self, model: str) -> set[str]:
        for entry in self.list_models():
            if entry.name == model:
                return set(entry.capabilities)
        return {"chat", "stream"}

    # -------------------------------------------------------------------------
    @staticmethod
    def tool_to_openai_schema(tool: LLMToolDefinition) -> dict[str, Any]:
        return {
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": OpenAIProvider._strict_parameters(
                tool.parameters_json_schema
            ),
            "strict": True,
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def _strict_parameters(schema: dict[str, Any]) -> dict[str, Any]:
        """Normalize JSON Schema for Responses strict function tools."""

        normalized = dict(schema)
        if normalized.get("type") == "object" or "properties" in normalized:
            properties = normalized.get("properties")
            if is_json_object(properties):
                normalized["properties"] = {
                    key: OpenAIProvider._strict_parameters(value)
                    if is_json_object(value)
                    else value
                    for key, value in properties.items()
                }
                normalized["required"] = list(properties.keys())
                normalized["additionalProperties"] = False
        if is_json_object(normalized.get("items")):
            normalized["items"] = OpenAIProvider._strict_parameters(normalized["items"])
        return normalized

    # -------------------------------------------------------------------------
    @staticmethod
    def normalize_tool_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for message in messages:
            if message.get("type") in {
                "function_call",
                "function_call_output",
                "reasoning",
            }:
                normalized.append(message)
                continue
            if message.get("type") == "message":
                content = message.get("content")
                if is_json_array(content):
                    text_parts = [
                        str(item.get("text") or "")
                        for raw_item in content
                        for item in [json_object(raw_item)]
                        if item and item.get("text") is not None
                    ]
                    normalized.append(
                        {
                            "role": str(message.get("role") or "assistant"),
                            "content": "".join(text_parts),
                        }
                    )
                    continue
            role = str(message.get("role") or "")
            if role == "assistant" and is_json_array(message.get("tool_calls")):
                for raw_call in json_array(message.get("tool_calls")):
                    call = json_object(raw_call)
                    if not call:
                        continue
                    call_id = str(call.get("id") or "")
                    normalized.append(
                        {
                            "type": "function_call",
                            "id": call_id or None,
                            "call_id": call_id,
                            "name": str(call.get("name") or ""),
                            "arguments": json.dumps(
                                call.get("arguments") or {}, separators=(",", ":")
                            ),
                        }
                    )
                continue
            if role == "tool":
                normalized.append(
                    {
                        "type": "function_call_output",
                        "call_id": message.get("tool_call_id"),
                        "output": str(message.get("content") or ""),
                    }
                )
                continue
            if role in {"system", "developer", "user", "assistant"}:
                normalized.append(
                    {
                        "role": role,
                        "content": str(message.get("content") or ""),
                    }
                )
                continue
            normalized.append(message)
        return normalized

    # -------------------------------------------------------------------------
    @staticmethod
    def _parse_tool_calls(raw: dict[str, Any]) -> list[LLMToolCall]:
        calls: list[LLMToolCall] = []
        for raw_item in json_array(raw.get("output")):
            item = json_object(raw_item)
            if not item or item.get("type") != "function_call":
                continue
            args: Any = item.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            calls.append(
                LLMToolCall(
                    id=item.get("call_id") or item.get("id"),
                    name=str(item.get("name") or ""),
                    arguments=json_object(args),
                )
            )
        return calls

    # -------------------------------------------------------------------------
    def chat(
        self,
        request: LLMRequest,
        *,
        tools: Sequence[LLMToolDefinition] | None = None,
        tool_choice: str | None = "auto",
        response_json_schema: dict[str, Any] | None = None,
    ) -> LLMResult:
        native_tools = list(tools or request.tools or [])
        schema = response_json_schema or request.response_json_schema
        effective_request = replace(
            request,
            tools=native_tools or None,
            response_json_schema=schema,
        )
        effective_request = prepare_request(
            effective_request, provider=self.provider_name
        )
        usage = compute_context_usage(effective_request, provider=self.provider_name)
        self._validate_request_capabilities(effective_request)
        kwargs: dict[str, Any] = {}
        if native_tools:
            kwargs["tools"] = [
                self.tool_to_openai_schema(tool) for tool in native_tools
            ]
            kwargs["tool_choice"] = tool_choice or request.tool_choice or "auto"
        if schema and not native_tools:
            kwargs["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "agent_response",
                    "schema": schema,
                    "strict": True,
                }
            }
        try:
            response = self._client_for_request(effective_request).responses.create(
                model=effective_request.model,
                input=self.normalize_tool_messages(effective_request.messages),
                temperature=effective_request.temperature,
                **kwargs,
            )
        except LLMStructuredOutputError:
            raise
        except Exception as exc:
            raise LLMProviderRequestError.from_exception(
                exc, provider=self.provider_name, model=request.model, stage="chat"
            ) from exc
        raw = dump_response_payload(response)
        usage = apply_reported_usage(usage, raw)
        return LLMResult(
            content=str(getattr(response, "output_text", "") or ""),
            raw=raw,
            tool_calls=self._parse_tool_calls(raw),
            finish_reason=raw.get("finish_reason") if is_json_object(raw) else None,
            context_usage=usage.to_dict(),
        )

    # -------------------------------------------------------------------------
    def stream_chat(self, request: LLMRequest) -> Iterable[str]:
        request = prepare_request(request, provider=self.provider_name)
        usage = compute_context_usage(request, provider=self.provider_name)
        stream: LLMTextStream

        def iterate() -> Iterable[str]:
            nonlocal usage
            try:
                response_stream = self._client_for_request(request).responses.create(
                    model=request.model,
                    input=request.messages,
                    temperature=request.temperature,
                    stream=True,
                )
                for event in response_stream:
                    remaining = remaining_request_seconds(request)
                    if remaining is not None and remaining <= 0:
                        raise TimeoutError(
                            "The bounded LLM request deadline has expired."
                        )
                    usage = apply_reported_usage(
                        usage,
                        dump_response_payload(event),
                    )
                    stream.context_usage = usage.to_dict()
                    if getattr(event, "type", None) != "response.output_text.delta":
                        continue
                    delta = getattr(event, "delta", "")
                    if delta:
                        yield str(delta)
            except LLMProviderRequestError:
                raise
            except Exception as exc:
                raise LLMProviderRequestError.from_exception(
                    exc,
                    provider=self.provider_name,
                    model=request.model,
                    stage="stream",
                ) from exc

        stream = LLMTextStream(iterate(), context_usage=usage.to_dict())
        return stream

    # -------------------------------------------------------------------------
    def structured_output(
        self, request: LLMRequest, schema: type[object]
    ) -> dict[str, Any]:
        schema_dump = getattr(schema, "model_json_schema", None)
        request_schema = json_object(schema_dump()) if callable(schema_dump) else {}
        request = prepare_request(
            replace(request, response_json_schema=request_schema),
            provider=self.provider_name,
        )
        usage = compute_context_usage(request, provider=self.provider_name)
        self._validate_request_capabilities(
            replace(request, response_json_schema=request_schema)
        )
        try:
            response = self._client_for_request(request).responses.parse(
                model=request.model,
                input=request.messages,
                temperature=request.temperature,
                text_format=schema,
            )
        except LLMStructuredOutputError:
            raise
        except Exception as exc:
            raise LLMProviderRequestError.from_exception(
                exc,
                provider=self.provider_name,
                model=request.model,
                stage="structured_output",
            ) from exc
        raw = dump_response_payload(response)
        usage = apply_reported_usage(usage, raw)
        parsed = getattr(response, "output_parsed", None)
        if is_json_object(parsed):
            return LLMStructuredOutput(parsed, context_usage=usage.to_dict())
        model_dump = getattr(parsed, "model_dump", None)
        if callable(model_dump):
            dumped = model_dump(mode="json")
            return LLMStructuredOutput(
                json_object(dumped), context_usage=usage.to_dict()
            )
        output_text = str(getattr(response, "output_text", "") or "")
        if output_text:
            try:
                loaded = json.loads(output_text)
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
            return LLMStructuredOutput(loaded, context_usage=usage.to_dict())
        return LLMStructuredOutput({}, context_usage=usage.to_dict())

    # -------------------------------------------------------------------------
    def embeddings(self, *, model: str, input_text: str) -> list[float]:
        response = self._client().embeddings.create(model=model, input=input_text)
        data = getattr(response, "data", None)
        if not data:
            return []
        embedding = getattr(data[0], "embedding", None)
        if not is_json_array(embedding):
            return []
        return [float(value) for value in embedding if isinstance(value, (int, float))]

    # -------------------------------------------------------------------------
    def health_check(self) -> dict[str, Any]:
        return {"ok": True, "detail": "configured"}
