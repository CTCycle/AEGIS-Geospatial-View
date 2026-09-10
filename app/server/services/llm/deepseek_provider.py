from __future__ import annotations

from server.common.typing import is_json_array, is_json_object, json_array, json_object

import asyncio
import json
import time
from collections.abc import Iterable, Sequence
from dataclasses import replace
from typing import Any, cast

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
RETIRED_DEEPSEEK_MODELS = frozenset({"deepseek-chat", "deepseek-reasoner"})

###############################################################################
class DeepSeekProvider(LLMProvider):
    provider_name = "deepseek"
    STRUCTURED_FUNCTION_NAME = "submit_structured_response"

    # -------------------------------------------------------------------------
    def __init__(self, *, api_key: str, base_url: str | None = None) -> None:
        self.api_key = api_key
        self.base_url = (base_url or DEFAULT_DEEPSEEK_BASE_URL).rstrip("/")
        self._declared_model_capabilities: dict[str, dict[str, bool]] = {}

    # -------------------------------------------------------------------------
    def _request_headers(self, request: LLMRequest | None = None) -> dict[str, str]:
        _ = request
        return {}

    # -------------------------------------------------------------------------
    def _client(self, request: LLMRequest | None = None) -> Any:
        kwargs: dict[str, Any] = {
            "api_key": self.api_key,
            "base_url": self.base_url,
            "timeout": 30.0,
            "max_retries": 0,
        }
        headers = self._request_headers(request)
        if headers:
            kwargs["default_headers"] = headers
        return OpenAI(**kwargs)

    # -------------------------------------------------------------------------
    def _async_client(self, request: LLMRequest | None = None) -> Any:
        kwargs: dict[str, Any] = {
            "api_key": self.api_key,
            "base_url": self.base_url,
            "timeout": 30.0,
            "max_retries": 0,
        }
        headers = self._request_headers(request)
        if headers:
            kwargs["default_headers"] = headers
        return AsyncOpenAI(**kwargs)

    # -------------------------------------------------------------------------
    def _client_for_request(self, request: LLMRequest) -> Any:
        try:
            client = self._client(request)
        except TypeError:
            # Keep small injected test clients and third-party adapters that
            # still expose the pre-request argument constructor usable.
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
    @staticmethod
    def _request_thinking_options(request: LLMRequest) -> dict[str, Any]:
        mode = str(request.metadata.get("thinking_mode") or "").strip().lower()
        if mode not in {"enabled", "disabled"}:
            return {}
        return {"extra_body": {"thinking": {"type": mode}}}

    # -------------------------------------------------------------------------
    def _validate_model_selection(self, request: LLMRequest) -> None:
        if request.model.strip().lower() in RETIRED_DEEPSEEK_MODELS:
            raise LLMProviderRequestError(
                provider=self.provider_name,
                model=request.model,
                stage="request_validation",
                code="provider_model_retired",
                retryable=False,
            )

    # -------------------------------------------------------------------------
    def list_models(self) -> list[ModelDescriptor]:
        response = httpx.get(
            f"{self.base_url}/models",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
            },
            timeout=5.0,
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
                self._declared_model_capabilities[model.name.lower()] = declared
        return models

    # -------------------------------------------------------------------------
    def supports_tools(self, model: str) -> bool | None:
        if model.strip().lower() in RETIRED_DEEPSEEK_MODELS:
            return False
        declared = self._declared_model_capabilities.get(model.strip().lower(), {}).get(
            "supports_tools"
        )
        if isinstance(declared, bool):
            return declared
        return True if model.strip().lower().startswith("deepseek-") else None

    # -------------------------------------------------------------------------
    def supports_structured_output(self, model: str) -> bool | None:
        if model.strip().lower() in RETIRED_DEEPSEEK_MODELS:
            return False
        declared = self._declared_model_capabilities.get(model.strip().lower(), {}).get(
            "supports_structured_output"
        )
        if isinstance(declared, bool):
            return declared
        return True if model.strip().lower().startswith("deepseek-") else None

    # -------------------------------------------------------------------------
    def _capabilities_for_model(self, model: str) -> set[str]:
        normalized = model.strip().lower()
        if normalized in RETIRED_DEEPSEEK_MODELS:
            return {"chat", "stream"}
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
        self._validate_model_selection(request)
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
        kwargs.update(self._request_thinking_options(effective_request))
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
        except LLMProviderRequestError:
            raise
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
        self._validate_model_selection(request)
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
            client = self._async_client(effective_request)
        except TypeError:
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
        except LLMProviderRequestError:
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
        self._validate_model_selection(request)
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
    def _uses_structured_function_transport(self) -> bool:
        return self.provider_name in {"opencode", "opencode-go"}

    # -------------------------------------------------------------------------
    def _structured_function_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.STRUCTURED_FUNCTION_NAME,
                "description": (
                    "Return exactly one top-level JSON object whose properties are "
                    "the extraction fields. Never wrap the arguments under "
                    "provider_contract, token, result, or any other key."
                ),
                "parameters": schema,
                "strict": True,
            },
        }

    # -------------------------------------------------------------------------
    def _parse_structured_payload(
        self,
        response: Any,
        schema: type[Any],
        request: LLMRequest,
        usage: Any,
    ) -> LLMStructuredOutput:
        content, tool_calls = self._parse_choice(response)
        if self._uses_structured_function_transport() and tool_calls:
            if content.strip():
                raise LLMResponseParsingError(
                    provider=self.provider_name,
                    model=request.model,
                    stage="structured_output",
                    code="structured_invalid_payload",
                    detail="The provider returned both structured function arguments and content.",
                    context_usage=usage.to_dict(),
                )
            if len(tool_calls) != 1:
                raise LLMResponseParsingError(
                    provider=self.provider_name,
                    model=request.model,
                    stage="structured_output",
                    code="structured_invalid_payload",
                    detail="The provider returned multiple structured extraction functions.",
                    context_usage=usage.to_dict(),
                )
            call = tool_calls[0]
            if call.name != self.STRUCTURED_FUNCTION_NAME or not call.arguments:
                raise LLMResponseParsingError(
                    provider=self.provider_name,
                    model=request.model,
                    stage="structured_output",
                    code="structured_invalid_payload",
                    detail="The provider returned an unexpected structured extraction function.",
                    context_usage=usage.to_dict(),
                )
            loaded: object = call.arguments
        else:
            try:
                loaded = json.loads(content or "{}")
            except (TypeError, json.JSONDecodeError) as exc:
                raise LLMResponseParsingError(
                    provider=self.provider_name,
                    model=request.model,
                    stage="structured_output",
                    code="structured_invalid_payload",
                    detail="The provider returned invalid JSON for structured extraction.",
                    context_usage=usage.to_dict(),
                ) from exc
        if not is_json_object(loaded):
            raise LLMResponseParsingError(
                provider=self.provider_name,
                model=request.model,
                stage="structured_output",
                code="structured_invalid_payload",
                detail="The provider returned a JSON value instead of an object.",
                context_usage=usage.to_dict(),
            )
        validator = getattr(schema, "model_validate", None)
        if not callable(validator):
            return LLMStructuredOutput(
                loaded,
                context_usage=usage.to_dict(),
                provided_fields=loaded.keys(),
            )
        try:
            validated = validator(loaded)
        except Exception as exc:  # noqa: BLE001
            validation_errors = getattr(exc, "errors", None)
            invalid_paths: list[str] = []
            if callable(validation_errors):
                try:
                    error_items: object = validation_errors()
                    if not isinstance(error_items, list):
                        error_items = []
                    for raw_item in cast(list[object], error_items):
                        if not is_json_object(raw_item):
                            continue
                        item = raw_item
                        raw_location = item.get("loc")
                        location_parts: Sequence[object] = (
                            cast(Sequence[object], raw_location)
                            if isinstance(raw_location, (list, tuple))
                            else ()
                        )
                        location = ".".join(
                            str(part) for part in location_parts
                        ).strip()
                        error_type = str(item.get("type") or "invalid").strip()
                        if location:
                            invalid_paths.append(f"{location} ({error_type})")
                except Exception:  # noqa: BLE001
                    invalid_paths = []
            detail = "The provider response did not match the requested extraction schema."
            if invalid_paths:
                detail += " Invalid fields: " + ", ".join(invalid_paths[:8]) + "."
            raise LLMResponseParsingError(
                provider=self.provider_name,
                model=request.model,
                stage="structured_output",
                code="structured_invalid_payload",
                detail=detail,
                context_usage=usage.to_dict(),
            ) from exc
        dumper = getattr(validated, "model_dump", None)
        payload = json_object(dumper(mode="json")) if callable(dumper) else loaded
        return LLMStructuredOutput(
            payload,
            context_usage=usage.to_dict(),
            provided_fields=loaded.keys(),
        )

    # -------------------------------------------------------------------------
    def structured_output(
        self, request: LLMRequest, schema: type[Any]
    ) -> dict[str, Any]:
        self._validate_model_selection(request)
        model_json_schema = getattr(schema, "model_json_schema", None)
        json_schema = (
            json_object(model_json_schema()) if callable(model_json_schema) else {}
        )
        metadata = dict(request.metadata)
        metadata[RESPONSE_SCHEMA_EMBEDDED_METADATA_KEY] = True
        function_transport = self._uses_structured_function_transport()
        request = prepare_request(
            replace(
                request,
                response_json_schema=None if function_transport else json_schema,
                messages=(
                    list(request.messages)
                    if function_transport
                    else self._messages_with_json_schema(request.messages, json_schema)
                ),
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
            if exc.code == "model_structured_output_unsupported":
                exc.code = "structured_schema_unsupported"
            exc.context_usage = usage.to_dict()
            raise
        try:
            max_tokens = self._request_max_tokens(request)
            request_kwargs: dict[str, Any] = {
                "model": request.model,
                "messages": self.normalize_tool_messages(request.messages),
                "temperature": request.temperature,
                "stream": False,
            }
            if function_transport:
                # OpenCode Go's thinking-mode models reject every explicit
                # ``tool_choice`` value (including the otherwise standard
                # forced-function object).  Supplying exactly one structured
                # function leaves the provider no other tool to select while
                # preserving its supported Chat Completions transport.  The
                # response parser remains strict about the function name,
                # cardinality, and typed payload.
                request_kwargs["tools"] = [
                    self._structured_function_schema(json_schema)
                ]
            else:
                request_kwargs["response_format"] = {"type": "json_object"}
            if max_tokens is not None:
                request_kwargs["max_tokens"] = max_tokens
            request_kwargs.update(self._request_thinking_options(request))
            response = self._client_for_request(request).chat.completions.create(
                **request_kwargs
            )
        except LLMProviderRequestError as exc:
            if exc.code == "provider_timeout":
                exc.code = "structured_timeout"
            raise
        except Exception as exc:
            error = LLMProviderRequestError.from_exception(
                exc,
                provider=self.provider_name,
                model=request.model,
                stage="structured_output",
                context_usage=usage.to_dict(),
            )
            if error.code == "provider_timeout":
                error.code = "structured_timeout"
            raise error from exc
        raw = dump_response_payload(response)
        usage = apply_reported_usage(usage, raw)
        return self._parse_structured_payload(response, schema, request, usage)

    # -------------------------------------------------------------------------
    async def astructured_output(
        self, request: LLMRequest, schema: type[Any]
    ) -> dict[str, Any]:
        self._validate_model_selection(request)
        model_json_schema = getattr(schema, "model_json_schema", None)
        json_schema = (
            json_object(model_json_schema()) if callable(model_json_schema) else {}
        )
        metadata = dict(request.metadata)
        metadata[RESPONSE_SCHEMA_EMBEDDED_METADATA_KEY] = True
        function_transport = self._uses_structured_function_transport()
        request = prepare_request(
            replace(
                request,
                response_json_schema=None if function_transport else json_schema,
                messages=(
                    list(request.messages)
                    if function_transport
                    else self._messages_with_json_schema(request.messages, json_schema)
                ),
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
            if exc.code == "model_structured_output_unsupported":
                exc.code = "structured_schema_unsupported"
            exc.context_usage = usage.to_dict()
            raise
        max_tokens = self._request_max_tokens(request)
        try:
            client = self._async_client(request)
        except TypeError:
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
            request_kwargs: dict[str, Any] = {
                "model": request.model,
                "messages": self.normalize_tool_messages(request.messages),
                "temperature": request.temperature,
                "stream": False,
            }
            if function_transport:
                request_kwargs["tools"] = [
                    self._structured_function_schema(json_schema)
                ]
            else:
                request_kwargs["response_format"] = {"type": "json_object"}
            if max_tokens is not None:
                request_kwargs["max_tokens"] = max_tokens
            request_kwargs.update(self._request_thinking_options(request))
            response = await request_client.chat.completions.create(**request_kwargs)
        except asyncio.CancelledError:
            raise
        except LLMProviderRequestError as exc:
            if exc.code == "provider_timeout":
                exc.code = "structured_timeout"
            raise
        except Exception as exc:
            error = LLMProviderRequestError.from_exception(
                exc,
                provider=self.provider_name,
                model=request.model,
                stage="structured_output",
                context_usage=usage.to_dict(),
                elapsed_ms=max(0, int((time.perf_counter() - started) * 1000)),
            )
            if error.code == "provider_timeout":
                error.code = "structured_timeout"
            raise error from exc
        finally:
            try:
                await client.close()
            except Exception:
                pass
        raw = dump_response_payload(response)
        usage = apply_reported_usage(usage, raw)
        return self._parse_structured_payload(response, schema, request, usage)

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
        if model_id.lower() in RETIRED_DEEPSEEK_MODELS:
            metadata["supports_tools"] = False
            metadata["supports_structured_output"] = False
            metadata["agent_selection_disabled_reason"] = (
                "DeepSeek retired this model. Select a model from the live catalog."
            )
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
