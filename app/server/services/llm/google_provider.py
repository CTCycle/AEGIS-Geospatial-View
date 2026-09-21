from __future__ import annotations

from server.common.typing import is_json_array, is_json_object, json_array, json_object

import asyncio
import json
from collections.abc import Iterable, Sequence
from dataclasses import replace
from typing import Any, cast

from google import genai
from google.genai import types as genai_types

from server.services.llm.base import (
    LLMProvider,
    normalize_native_tool_name,
    parse_native_tool_arguments,
)
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
from server.services.llm.transport import (
    LLMTransportPolicy,
    close_sync_client,
)
from server.services.llm.types import (
    LLMRequest,
    LLMResult,
    LLMStructuredOutput,
    LLMTextStream,
    LLMToolCall,
    LLMToolDefinition,
    ModelDescriptor,
)

DEFAULT_GOOGLE_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

###############################################################################
class GoogleProvider(LLMProvider):
    provider_name = "google"

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        transport_policy: LLMTransportPolicy | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = (base_url or DEFAULT_GOOGLE_BASE_URL).rstrip("/")
        self.transport_policy = transport_policy or LLMTransportPolicy()

    # -------------------------------------------------------------------------
    def _client(
        self,
        *,
        timeout_seconds: float | None = None,
        stage: str = "chat",
    ) -> Any:
        http_options_constructor: Any = genai_types.HttpOptions
        timeout = (
            self.transport_policy.timeout_for(stage)
            if timeout_seconds is None
            else timeout_seconds
        )
        options: dict[str, Any] = {
            "timeout": max(1, int(timeout * 1000)),
            "retryOptions": genai_types.HttpRetryOptions(attempts=1),
            "clientArgs": self.transport_policy.client_args(),
        }
        if self.base_url and self.base_url != DEFAULT_GOOGLE_BASE_URL:
            options.update({"baseUrl": self.base_url, "apiVersion": "v1beta"})
        return genai.Client(
            api_key=self.api_key,
            http_options=http_options_constructor(**options),
        )

    # -------------------------------------------------------------------------
    def _client_for_request(
        self, request: LLMRequest, *, stage: str = "chat"
    ) -> Any:
        remaining = remaining_request_seconds(request)
        if remaining is None:
            return self._client(stage=stage)
        if remaining <= 0:
            raise TimeoutError("The bounded LLM request deadline has expired.")
        return self._client(timeout_seconds=remaining, stage=stage)

    # -------------------------------------------------------------------------
    async def achat(
        self,
        request: LLMRequest,
        *,
        tools: Sequence[LLMToolDefinition] | None = None,
        tool_choice: str | None = "auto",
        response_json_schema: dict[str, Any] | None = None,
    ) -> LLMResult:
        return await asyncio.to_thread(
            self.chat,
            request,
            tools=tools,
            tool_choice=tool_choice,
            response_json_schema=response_json_schema,
        )

    # -------------------------------------------------------------------------
    async def astructured_output(
        self, request: LLMRequest, schema: type[Any]
    ) -> dict[str, Any]:
        return await asyncio.to_thread(self.structured_output, request, schema)

    # -------------------------------------------------------------------------
    def list_models(self) -> list[ModelDescriptor]:
        return [
            entry for entry in get_cloud_model_catalog() if entry.provider == "google"
        ]

    # -------------------------------------------------------------------------
    def get_model_context_metadata(self, model: str) -> dict[str, Any]:
        """Read the selected model's documented GenAI token limits."""

        client: Any | None = None
        try:
            client = self._client(stage="catalog")
            if client is None:
                return {}
            try:
                descriptor: object = client.models.get(model=model)
            except TypeError:
                descriptor = client.models.get(name=model)
            metadata: dict[str, Any] = {
                "context_profile_source": "google_models_api",
                "context_metadata_authority": "provider",
            }
            for index, value in enumerate(
                self._model_fields(
                    descriptor, "input_token_limit", "inputTokenLimit"
                ).values()
            ):
                metadata["context_window_tokens" if index == 0 else "context_length"] = value
            for index, value in enumerate(
                self._model_fields(
                    descriptor, "output_token_limit", "outputTokenLimit"
                ).values()
            ):
                metadata[
                    "maximum_output_tokens" if index == 0 else "max_output_tokens"
                ] = value
            return metadata if len(metadata) > 2 else {}
        finally:
            if client is not None:
                close_sync_client(client)

    # -------------------------------------------------------------------------
    @staticmethod
    def _model_fields(
        value: object, snake_key: str, camel_key: str
    ) -> dict[str, object]:
        if isinstance(value, dict):
            mapping = cast(dict[str, object], value)
            return {
                key: mapping[key]
                for key in (snake_key, camel_key)
                if key in mapping
            }
        result: dict[str, object] = {}
        snake_value = getattr(value, snake_key, None)
        camel_value = getattr(value, camel_key, None)
        if snake_value is not None:
            result[snake_key] = snake_value
        if camel_value is not None:
            result[camel_key] = camel_value
        return result

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
    def tool_to_google_schema(tool: LLMToolDefinition) -> dict[str, Any]:
        return {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters_json_schema,
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def _parse_tool_calls(raw: dict[str, Any]) -> list[LLMToolCall]:
        calls: list[LLMToolCall] = []
        candidates = raw.get("candidates") if is_json_object(raw) else None
        for candidate in json_array(candidates):
            candidate_object = json_object(candidate)
            content = json_object(candidate_object.get("content"))
            for part in json_array(content.get("parts")):
                part_object = json_object(part)
                function_call = part_object.get("functionCall") or part_object.get(
                    "function_call"
                )
                if not is_json_object(function_call):
                    continue
                args, parse_error = parse_native_tool_arguments(
                    function_call.get("args")
                )
                name, parse_error = normalize_native_tool_name(
                    function_call.get("name"), parse_error
                )
                calls.append(
                    LLMToolCall(
                        id=function_call.get("id"),
                        name=name,
                        arguments=args,
                        parse_error=parse_error,
                    )
                )
        return calls

    # -------------------------------------------------------------------------
    @staticmethod
    def normalize_tool_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return messages

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
        config = self._config_from_request(effective_request)
        try:
            self._validate_request_capabilities(effective_request)
        except LLMStructuredOutputError as exc:
            exc.context_usage = usage.to_dict()
            raise
        if native_tools:
            config["tools"] = [
                {
                    "function_declarations": [
                        self.tool_to_google_schema(tool) for tool in native_tools
                    ]
                }
            ]
            choice = tool_choice or request.tool_choice or "auto"
            mode = (
                "ANY"
                if choice == "required"
                else "NONE"
                if choice == "none"
                else "AUTO"
            )
            config["tool_config"] = {"function_calling_config": {"mode": mode}}
        if schema and not native_tools:
            config["response_mime_type"] = "application/json"
            config["response_json_schema"] = schema
        client: Any | None = None
        try:
            client = self._client_for_request(effective_request, stage="chat")
            if client is None:
                raise RuntimeError("Google client was not initialized.")
            response = client.models.generate_content(
                model=effective_request.model,
                contents=self._contents_from_messages(effective_request.messages),
                config=config,
            )
        except LLMStructuredOutputError:
            raise
        except Exception as exc:
            raise LLMProviderRequestError.from_exception(
                exc,
                provider=self.provider_name,
                model=request.model,
                stage="chat",
                context_usage=usage.to_dict(),
            ) from exc
        finally:
            if client is not None:
                close_sync_client(client)
        raw = dump_response_payload(response)
        usage = apply_reported_usage(usage, raw)
        return LLMResult(
            content=str(getattr(response, "text", "") or ""),
            raw=raw,
            tool_calls=self._parse_tool_calls(raw),
            finish_reason=self._extract_finish_reason(raw),
            context_usage=usage.to_dict(),
        )

    # -------------------------------------------------------------------------
    def stream_chat(self, request: LLMRequest) -> Iterable[str]:
        request = prepare_request(request, provider=self.provider_name)
        usage = compute_context_usage(request, provider=self.provider_name)
        stream: LLMTextStream

        def iterate() -> Iterable[str]:
            nonlocal usage
            client: Any | None = None
            try:
                client = self._client_for_request(request, stage="stream")
                if client is None:
                    raise RuntimeError("Google client was not initialized.")
                response_stream = client.models.generate_content_stream(
                    model=request.model,
                    contents=self._contents_from_messages(request.messages),
                    config=self._config_from_request(request),
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
                    text = getattr(chunk, "text", "")
                    if text:
                        yield str(text)
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
            finally:
                if client is not None:
                    close_sync_client(client)

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
        request = prepare_request(
            replace(request, response_json_schema=json_schema),
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
        client: Any | None = None
        try:
            client = self._client_for_request(request, stage="structured_output")
            if client is None:
                raise RuntimeError("Google client was not initialized.")
            response = client.models.generate_content(
                model=request.model,
                contents=self._contents_from_messages(request.messages),
                config={
                    **self._config_from_request(request),
                    "response_mime_type": "application/json",
                    "response_json_schema": json_schema,
                },
            )
        except LLMStructuredOutputError:
            raise
        except Exception as exc:
            raise LLMProviderRequestError.from_exception(
                exc,
                provider=self.provider_name,
                model=request.model,
                stage="structured_output",
                context_usage=usage.to_dict(),
            ) from exc
        finally:
            if client is not None:
                close_sync_client(client)
        raw = dump_response_payload(response)
        usage = apply_reported_usage(usage, raw)
        try:
            loaded = json.loads(str(getattr(response, "text", "") or "{}"))
        except (TypeError, json.JSONDecodeError) as exc:
            raise LLMResponseParsingError(
                provider=self.provider_name,
                model=request.model,
                stage="structured_output",
                detail="The provider returned invalid JSON for the structured native response.",
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
        return LLMStructuredOutput(
            loaded,
            context_usage=usage.to_dict(),
            provided_fields=loaded.keys(),
        )

    # -------------------------------------------------------------------------
    def embeddings(self, *, model: str, input_text: str) -> list[float]:
        client: Any | None = None
        try:
            client = self._client(stage="embeddings")
            if client is None:
                raise RuntimeError("Google client was not initialized.")
            response = client.models.embed_content(model=model, contents=input_text)
        except LLMProviderRequestError:
            raise
        except Exception as exc:
            raise LLMProviderRequestError.from_exception(
                exc,
                provider=self.provider_name,
                model=model,
                stage="embeddings",
            ) from exc
        finally:
            if client is not None:
                close_sync_client(client)
        embeddings = getattr(response, "embeddings", None)
        if embeddings:
            values = getattr(embeddings[0], "values", None)
            if is_json_array(values):
                return [
                    float(value) for value in values if isinstance(value, (int, float))
                ]
        embedding = getattr(response, "embedding", None)
        values = getattr(embedding, "values", None)
        if is_json_array(values):
            return [float(value) for value in values if isinstance(value, (int, float))]
        raise LLMProviderRequestError(
            provider=self.provider_name,
            model=model,
            stage="embeddings",
            code="provider_invalid_response",
            retryable=False,
        )

    # -------------------------------------------------------------------------
    def health_check(self) -> dict[str, Any]:
        return {"ok": True, "detail": "configured"}

    # -------------------------------------------------------------------------
    @staticmethod
    def _contents_from_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        contents: list[dict[str, Any]] = []
        for message in messages:
            role = str(message.get("role") or "").strip().lower()
            if role == "system":
                continue
            if role == "assistant" and is_json_array(message.get("tool_calls")):
                contents.append(
                    {
                        "role": "model",
                        "parts": [
                            {
                                "function_call": {
                                    "name": call.get("name"),
                                    "args": call.get("arguments") or {},
                                }
                            }
                            for call in message["tool_calls"]
                            if is_json_object(call)
                        ],
                    }
                )
                continue
            if role == "tool":
                contents.append(
                    {
                        "role": "user",
                        "parts": [
                            {
                                "function_response": {
                                    "name": message.get("name"),
                                    "response": {"content": message.get("content")},
                                }
                            }
                        ],
                    }
                )
                continue
            mapped_role = "model" if role == "assistant" else "user"
            contents.append(
                {
                    "role": mapped_role,
                    "parts": [{"text": str(message.get("content") or "")}],
                }
            )
        return contents or [{"role": "user", "parts": [{"text": ""}]}]

    # -------------------------------------------------------------------------
    @staticmethod
    def _extract_finish_reason(raw: dict[str, Any]) -> str | None:
        candidates = raw.get("candidates") if is_json_object(raw) else None
        if not is_json_array(candidates) or not candidates:
            return None
        candidate = candidates[0]
        if not is_json_object(candidate):
            return None
        reason = candidate.get("finishReason") or candidate.get("finish_reason")
        return str(reason) if reason else None

    # -------------------------------------------------------------------------
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
