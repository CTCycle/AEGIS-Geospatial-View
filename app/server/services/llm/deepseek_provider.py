from __future__ import annotations

from server.common.typing import is_json_array, is_json_object, json_array, json_object

import asyncio
import json
import time
from collections.abc import Iterable, Sequence
from dataclasses import replace
from typing import Any

import httpx
from openai import AsyncOpenAI, OpenAI

from server.services.llm.base import LLMProvider
from server.services.llm.context_budget import (
    apply_reported_usage,
    compute_context_usage,
    prepare_request,
    RESPONSE_SCHEMA_EMBEDDED_METADATA_KEY,
)
from server.prompts.providers import build_deepseek_json_schema_instruction
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

DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"


###############################################################################
class DeepSeekProvider(LLMProvider):
    provider_name = "deepseek"

    # -------------------------------------------------------------------------
    def __init__(self, *, api_key: str, base_url: str | None = None) -> None:
        self.api_key = api_key
        self.base_url = (base_url or DEFAULT_DEEPSEEK_BASE_URL).rstrip("/")
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
    def _async_client(self) -> Any:
        return AsyncOpenAI(
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
            return with_options(timeout=remaining)
        return client

    # -------------------------------------------------------------------------
    @staticmethod
    def _request_max_tokens(request: LLMRequest) -> int | None:
        def positive_int(value: object) -> int | None:
            if isinstance(value, bool):
                return None
            try:
                parsed = int(value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return None
            return parsed if parsed > 0 else None

        metadata = request.metadata
        configured = positive_int(
            metadata.get("max_tokens")
            or metadata.get("max_output_tokens")
            or metadata.get("max_completion_tokens")
        )
        maximum = positive_int(metadata.get("maximum_output_tokens"))
        if configured is None:
            return None
        return min(configured, maximum) if maximum is not None else configured

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
        declared = self._declared_model_capabilities.get(model, {}).get(
            "supports_tools"
        )
        if isinstance(declared, bool):
            return declared
        return True if model.strip().lower().startswith("deepseek-") else None

    # -------------------------------------------------------------------------
    def supports_structured_output(self, model: str) -> bool | None:
        declared = self._declared_model_capabilities.get(model, {}).get(
            "supports_structured_output"
        )
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
        native_tools = list(tools or request.tools or [])
        schema = response_json_schema or request.response_json_schema
        metadata = dict(request.metadata)
        if schema and not native_tools:
            metadata[RESPONSE_SCHEMA_EMBEDDED_METADATA_KEY] = True
        effective_request = replace(
            request,
            tools=native_tools or None,
            response_json_schema=schema,
            metadata=metadata,
        )
        if schema and not native_tools:
            effective_request = replace(
                effective_request,
                messages=self._messages_with_json_schema(
                    effective_request.messages, schema
                ),
            )
        effective_request = prepare_request(
            effective_request, provider=self.provider_name
        )
        usage = compute_context_usage(effective_request, provider=self.provider_name)
        try:
            self._validate_request_capabilities(effective_request)
        except LLMStructuredOutputError as exc:
            exc.context_usage = usage.to_dict()
            raise
        kwargs: dict[str, Any] = {}
        max_tokens = self._request_max_tokens(effective_request)
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if native_tools:
            kwargs["tools"] = [
                self.tool_to_openai_schema(tool) for tool in native_tools
            ]
            kwargs["tool_choice"] = tool_choice or request.tool_choice or "auto"
        if schema and not native_tools:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            response = self._client_for_request(effective_request).chat.completions.create(
                model=effective_request.model,
                messages=self.normalize_tool_messages(effective_request.messages),
                temperature=effective_request.temperature,
                stream=False,
                **kwargs,
            )
        except Exception as exc:
            raise LLMProviderRequestError.from_exception(
                exc,
                provider=self.provider_name,
                model=request.model,
                stage="chat",
                context_usage=usage.to_dict(),
            ) from exc
        raw = dump_response_payload(response)
        usage = apply_reported_usage(usage, raw)
        content, tool_calls = self._parse_choice(response)
        return LLMResult(
            content=content,
            raw=raw,
            tool_calls=tool_calls,
            finish_reason=self._finish_reason(response),
            context_usage=usage.to_dict(),
        )

    # -------------------------------------------------------------------------
    async def achat(
        self,
        request: LLMRequest,
        *,
        tools: Sequence[LLMToolDefinition] | None = None,
        tool_choice: str | None = "auto",
        response_json_schema: dict[str, Any] | None = None,
    ) -> LLMResult:
        native_tools = list(tools or request.tools or [])
        schema = response_json_schema or request.response_json_schema
        metadata = dict(request.metadata)
        if schema and not native_tools:
            metadata[RESPONSE_SCHEMA_EMBEDDED_METADATA_KEY] = True
        effective_request = replace(
            request,
            tools=native_tools or None,
            response_json_schema=schema,
            metadata=metadata,
        )
        if schema and not native_tools:
            effective_request = replace(
                effective_request,
                messages=self._messages_with_json_schema(
                    effective_request.messages, schema
                ),
            )
        effective_request = prepare_request(
            effective_request, provider=self.provider_name
        )
        usage = compute_context_usage(effective_request, provider=self.provider_name)
        try:
            self._validate_request_capabilities(effective_request)
        except LLMStructuredOutputError as exc:
            exc.context_usage = usage.to_dict()
            raise
        kwargs: dict[str, Any] = {}
        max_tokens = self._request_max_tokens(effective_request)
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if native_tools:
            kwargs["tools"] = [
                self.tool_to_openai_schema(tool) for tool in native_tools
            ]
            kwargs["tool_choice"] = tool_choice or request.tool_choice or "auto"
        if schema and not native_tools:
            kwargs["response_format"] = {"type": "json_object"}
        client = self._async_client()
        started = time.perf_counter()
        try:
            request_client: Any = client
            remaining = remaining_request_seconds(effective_request)
            if remaining is not None:
                if remaining <= 0:
                    raise TimeoutError("The bounded LLM request deadline has expired.")
                with_options = getattr(client, "with_options", None)
                if callable(with_options):
                    request_client = with_options(timeout=remaining)
            response = await request_client.chat.completions.create(
                model=effective_request.model,
                messages=self.normalize_tool_messages(effective_request.messages),
                temperature=effective_request.temperature,
                stream=False,
                **kwargs,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise LLMProviderRequestError.from_exception(
                exc,
                provider=self.provider_name,
                model=request.model,
                stage="chat",
                context_usage=usage.to_dict(),
                elapsed_ms=max(0, int((time.perf_counter() - started) * 1000)),
            ) from exc
        finally:
            try:
                await client.close()
            except Exception:
                pass
        raw = dump_response_payload(response)
        usage = apply_reported_usage(usage, raw)
        content, tool_calls = self._parse_choice(response)
        return LLMResult(
            content=content,
            raw=raw,
            tool_calls=tool_calls,
            finish_reason=self._finish_reason(response),
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
                max_tokens = self._request_max_tokens(request)
                response_stream = self._client_for_request(
                    request
                ).chat.completions.create(
                    model=request.model,
                    messages=self.normalize_tool_messages(request.messages),
                    temperature=request.temperature,
                    stream=True,
                    stream_options={"include_usage": True},
                    **({"max_tokens": max_tokens} if max_tokens is not None else {}),
                )
                for chunk in response_stream:
                    remaining = remaining_request_seconds(request)
                    if remaining is not None and remaining <= 0:
                        raise TimeoutError(
                            "The bounded LLM request deadline has expired."
                        )
                    usage = apply_reported_usage(
                        usage,
                        dump_response_payload(chunk),
                    )
                    stream.context_usage = usage.to_dict()
                    delta = (
                        chunk.choices[0].delta
                        if getattr(chunk, "choices", None)
                        else None
                    )
                    text = getattr(delta, "content", None)
                    if isinstance(text, str) and text:
                        yield text
            except LLMProviderRequestError:
                raise
            except Exception as exc:
                raise LLMProviderRequestError.from_exception(
                    exc,
                    provider=self.provider_name,
                    model=request.model,
                    stage="stream",
                    context_usage=usage.to_dict(),
                ) from exc

        stream = LLMTextStream(iterate(), context_usage=usage.to_dict())
        return stream

    # -------------------------------------------------------------------------
    def structured_output(
        self, request: LLMRequest, schema: type[Any]
    ) -> dict[str, Any]:
        model_json_schema = getattr(schema, "model_json_schema", None)
        json_schema = (
            json_object(model_json_schema()) if callable(model_json_schema) else {}
        )
        metadata = dict(request.metadata)
        metadata[RESPONSE_SCHEMA_EMBEDDED_METADATA_KEY] = True
        request = prepare_request(
            replace(
                request,
                response_json_schema=json_schema,
                messages=self._messages_with_json_schema(request.messages, json_schema),
                metadata=metadata,
            ),
            provider=self.provider_name,
        )
        usage = compute_context_usage(request, provider=self.provider_name)
        try:
            self._validate_request_capabilities(
                replace(request, response_json_schema=json_schema)
            )
        except LLMStructuredOutputError as exc:
            exc.context_usage = usage.to_dict()
            raise
        try:
            max_tokens = self._request_max_tokens(request)
            response = self._client_for_request(request).chat.completions.create(
                model=request.model,
                messages=self.normalize_tool_messages(request.messages),
                temperature=request.temperature,
                response_format={"type": "json_object"},
                stream=False,
                **({"max_tokens": max_tokens} if max_tokens is not None else {}),
            )
        except Exception as exc:
            raise LLMProviderRequestError.from_exception(
                exc,
                provider=self.provider_name,
                model=request.model,
                stage="structured_output",
                context_usage=usage.to_dict(),
            ) from exc
        raw = dump_response_payload(response)
        usage = apply_reported_usage(usage, raw)
        content, _ = self._parse_choice(response)
        try:
            loaded = json.loads(content or "{}")
        except (TypeError, json.JSONDecodeError) as exc:
            raise LLMResponseParsingError(
                provider=self.provider_name,
                model=request.model,
                stage="structured_output",
                detail="The provider returned invalid JSON for structured extraction.",
                context_usage=usage.to_dict(),
            ) from exc
        if not is_json_object(loaded):
            raise LLMResponseParsingError(
                provider=self.provider_name,
                model=request.model,
                stage="structured_output",
                detail="The provider returned a JSON value instead of an object.",
                context_usage=usage.to_dict(),
            )
        validator = getattr(schema, "model_validate", None)
        if not callable(validator):
            return LLMStructuredOutput(loaded, context_usage=usage.to_dict())
        try:
            validated = validator(loaded)
        except Exception as exc:  # noqa: BLE001
            raise LLMResponseParsingError(
                provider=self.provider_name,
                model=request.model,
                stage="structured_output",
                detail="The provider response did not match the requested extraction schema.",
                context_usage=usage.to_dict(),
            ) from exc
        dumper = getattr(validated, "model_dump", None)
        payload = json_object(dumper(mode="json")) if callable(dumper) else loaded
        return LLMStructuredOutput(payload, context_usage=usage.to_dict())

    # -------------------------------------------------------------------------
    async def astructured_output(
        self, request: LLMRequest, schema: type[Any]
    ) -> dict[str, Any]:
        model_json_schema = getattr(schema, "model_json_schema", None)
        json_schema = (
            json_object(model_json_schema()) if callable(model_json_schema) else {}
        )
        metadata = dict(request.metadata)
        metadata[RESPONSE_SCHEMA_EMBEDDED_METADATA_KEY] = True
        request = prepare_request(
            replace(
                request,
                response_json_schema=json_schema,
                messages=self._messages_with_json_schema(request.messages, json_schema),
                metadata=metadata,
            ),
            provider=self.provider_name,
        )
        usage = compute_context_usage(request, provider=self.provider_name)
        try:
            self._validate_request_capabilities(
                replace(request, response_json_schema=json_schema)
            )
        except LLMStructuredOutputError as exc:
            exc.context_usage = usage.to_dict()
            raise
        max_tokens = self._request_max_tokens(request)
        client = self._async_client()
        started = time.perf_counter()
        try:
            request_client: Any = client
            remaining = remaining_request_seconds(request)
            if remaining is not None:
                if remaining <= 0:
                    raise TimeoutError("The bounded LLM request deadline has expired.")
                with_options = getattr(client, "with_options", None)
                if callable(with_options):
                    request_client = with_options(timeout=remaining)
            response = await request_client.chat.completions.create(
                model=request.model,
                messages=self.normalize_tool_messages(request.messages),
                temperature=request.temperature,
                response_format={"type": "json_object"},
                stream=False,
                **({"max_tokens": max_tokens} if max_tokens is not None else {}),
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise LLMProviderRequestError.from_exception(
                exc,
                provider=self.provider_name,
                model=request.model,
                stage="structured_output",
                context_usage=usage.to_dict(),
                elapsed_ms=max(0, int((time.perf_counter() - started) * 1000)),
            ) from exc
        finally:
            try:
                await client.close()
            except Exception:
                pass
        raw = dump_response_payload(response)
        usage = apply_reported_usage(usage, raw)
        content, _ = self._parse_choice(response)
        try:
            loaded = json.loads(content or "{}")
        except (TypeError, json.JSONDecodeError) as exc:
            raise LLMResponseParsingError(
                provider=self.provider_name,
                model=request.model,
                stage="structured_output",
                detail="The provider returned invalid JSON for structured extraction.",
                context_usage=usage.to_dict(),
            ) from exc
        if not is_json_object(loaded):
            raise LLMResponseParsingError(
                provider=self.provider_name,
                model=request.model,
                stage="structured_output",
                detail="The provider returned a JSON value instead of an object.",
                context_usage=usage.to_dict(),
            )
        validator = getattr(schema, "model_validate", None)
        if not callable(validator):
            return LLMStructuredOutput(loaded, context_usage=usage.to_dict())
        try:
            validated = validator(loaded)
        except Exception as exc:
            raise LLMResponseParsingError(
                provider=self.provider_name,
                model=request.model,
                stage="structured_output",
                detail="The provider response did not match the requested extraction schema.",
                context_usage=usage.to_dict(),
            ) from exc
        dumper = getattr(validated, "model_dump", None)
        payload = json_object(dumper(mode="json")) if callable(dumper) else loaded
        return LLMStructuredOutput(payload, context_usage=usage.to_dict())

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
            "context_window",
            "max_context_tokens",
            "maximum_output_tokens",
            "max_output_tokens",
            "max_completion_tokens",
        ):
            if item.get(key) is not None:
                metadata[key] = item[key]
        if any(
            key in metadata
            for key in (
                "context_window_tokens",
                "context_length",
                "context_window",
                "max_context_tokens",
                "maximum_output_tokens",
                "max_output_tokens",
                "max_completion_tokens",
            )
        ):
            metadata["context_profile_source"] = "provider_models_api"
        raw_capabilities = item.get("capabilities")
        if is_json_array(raw_capabilities):
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
            return (
                "Fast DeepSeek model for responsive chat, extraction, and agent tasks."
            )
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
