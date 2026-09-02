from __future__ import annotations

from server.common.typing import is_json_array, is_json_object, json_array, json_object

import json
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import replace
from html.parser import HTMLParser
from typing import Any, TextIO
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from server.services.llm.base import LLMProvider
from server.services.llm.context_budget import (
    apply_reported_usage,
    compute_context_usage,
    prepare_request,
)
from server.prompts.providers import OLLAMA_TOOL_CAPABILITY_PROBE_PROMPT
from server.services.llm.errors import (
    LLMProviderRequestError,
    LLMResponseParsingError,
    LLMStructuredOutputError,
)
from server.services.llm.ollama_capability_cache import OllamaToolCapabilityCache
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
class _OllamaLibraryParser(HTMLParser):
    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        super().__init__()
        self._active_model: str | None = None
        self._chunks: list[str] = []
        self.entries: dict[str, str] = {}

    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    def handle_data(self, data: str) -> None:
        if self._active_model is None:
            return
        text = data.strip()
        if text:
            self._chunks.append(text)

    # -------------------------------------------------------------------------
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


###############################################################################
class OllamaProvider(LLMProvider):
    provider_name = "ollama"

    # Local structured extraction can include the full orchestration schema and
    # needs more time than lightweight health, capability, and chat probes.
    _DEFAULT_REQUEST_TIMEOUT_SECONDS = 30
    _STRUCTURED_REQUEST_TIMEOUT_SECONDS = 90

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        base_url: str,
        tool_capability_cache: OllamaToolCapabilityCache | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.tool_capability_cache = (
            tool_capability_cache or OllamaToolCapabilityCache()
        )
        self.last_list_models_error: str | None = None
        self._show_payload_cache: dict[str, dict[str, Any] | None] = {}

    # -------------------------------------------------------------------------
    def _post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        default_timeout = (
            self._STRUCTURED_REQUEST_TIMEOUT_SECONDS
            if path == "/api/chat" and payload.get("format")
            else self._DEFAULT_REQUEST_TIMEOUT_SECONDS
        )
        effective_timeout = default_timeout if timeout is None else min(
            default_timeout, max(0.1, timeout)
        )
        with urlopen(request, timeout=effective_timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    # -------------------------------------------------------------------------
    def _stream_post(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        timeout: float | None = None,
    ) -> Iterator[dict[str, Any]]:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        effective_timeout = 60.0 if timeout is None else min(60.0, max(0.1, timeout))
        with urlopen(request, timeout=effective_timeout) as response:
            reader: TextIO = response  # type: ignore[assignment]
            for line in reader:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    pass

    # -------------------------------------------------------------------------
    def _get_json(self, path: str) -> dict[str, Any]:
        request = Request(f"{self.base_url}{path}", method="GET")
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    # -------------------------------------------------------------------------
    def _get_text(self, url: str) -> str:
        request = Request(url, headers={"User-Agent": "AEGIS/1.0"}, method="GET")
        with urlopen(request, timeout=20) as response:
            return response.read().decode("utf-8", errors="ignore")

    # -------------------------------------------------------------------------
    def _post_json_for_request(
        self, path: str, payload: dict[str, Any], request: LLMRequest
    ) -> dict[str, Any]:
        remaining = remaining_request_seconds(request)
        if remaining is None:
            return self._post_json(path, payload)
        if remaining <= 0:
            raise TimeoutError("The bounded LLM request deadline has expired.")
        return self._post_json(path, payload, timeout=remaining)

    # -------------------------------------------------------------------------
    def _stream_post_for_request(
        self, path: str, payload: dict[str, Any], request: LLMRequest
    ) -> Iterator[dict[str, Any]]:
        remaining = remaining_request_seconds(request)
        if remaining is None:
            yield from self._stream_post(path, payload)
            return
        if remaining <= 0:
            raise TimeoutError("The bounded LLM request deadline has expired.")
        yield from self._stream_post(path, payload, timeout=remaining)

    # -------------------------------------------------------------------------
    def list_models(self) -> list[ModelDescriptor]:
        try:
            payload = self._get_json("/api/tags")
        except Exception as exc:
            self.last_list_models_error = (
                str(exc) or f"Unable to reach Ollama at {self.base_url}."
            )
            return []
        self.last_list_models_error = None
        models: list[ModelDescriptor] = []
        for item in payload.get("models", []):
            if not is_json_object(item):
                continue
            model_name = str(item.get("name") or "")
            if not model_name:
                continue
            details = json_object(item.get("details"))
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
                    tag_capabilities=item.get("capabilities")
                    if is_json_array(item.get("capabilities"))
                    else None,
                )
            )
        return models

    # -------------------------------------------------------------------------
    def _descriptor_from_tag_item(
        self,
        *,
        item: dict[str, Any],
        model_name: str,
        description: str,
        family: str,
        parameter_size: str,
        quantization_level: str,
        tag_capabilities: Sequence[str] | None = None,
    ) -> ModelDescriptor:
        if tag_capabilities is not None:
            capabilities = {
                str(value).strip().lower()
                for value in tag_capabilities
                if str(value).strip()
            }
            capabilities.update({"chat", "stream", "structured_output"})
            if "embedding" in capabilities:
                capabilities.add("embeddings")
        else:
            capabilities = self.get_model_capabilities(model_name)
        supports_tools: bool | None = (
            "tools" in capabilities
            if tag_capabilities is not None
            else self.supports_tools(model_name)
        )
        if supports_tools is True:
            capabilities.add("tools")
        source = (
            "ollama_tags"
            if tag_capabilities is not None
            else self._tool_support_source(model_name)
        )
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

    # -------------------------------------------------------------------------
    def get_model_capabilities(self, model: str) -> set[str]:
        capabilities = {"chat", "stream", "structured_output", "embeddings"}
        show_capabilities = self._show_capabilities(model)
        if show_capabilities is not None:
            if "tools" in show_capabilities:
                capabilities.add("tools")
            if "vision" in show_capabilities:
                capabilities.add("vision")
            if "embedding" in show_capabilities:
                capabilities.add("embeddings")
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

    # -------------------------------------------------------------------------
    def supports_tools(self, model: str) -> bool | None:
        show_capabilities = self._show_capabilities(model)
        if show_capabilities is not None:
            supported = "tools" in show_capabilities
            self.tool_capability_cache.set(
                self.base_url,
                model,
                supported,
                source="ollama_show",
            )
            return supported
        return self._probe_tool_support(model)

    # -------------------------------------------------------------------------
    def supports_structured_output(self, model: str) -> bool | None:
        _ = model
        return True

    # -------------------------------------------------------------------------
    def get_model_context_metadata(self, model: str) -> dict[str, Any]:
        """Read an exact context declaration from Ollama's model metadata.

        Ollama's tags endpoint does not expose the model context window.  The
        show endpoint may expose it in ``model_info`` (for example as
        ``general.context_length``).  Only that provider-declared value is
        accepted; model names, families, and Modelfile text are intentionally
        not interpreted as limits.
        """

        payload = self._show_payload(model)
        if payload is None:
            return {}
        model_info = json_object(payload.get("model_info"))
        candidates: list[object] = []
        for key, value in model_info.items():
            normalized_key = str(key).strip().lower()
            if normalized_key.endswith((".context_length", ".context_window_tokens")):
                candidates.append(value)
        for key in ("context_window_tokens", "context_length"):
            if payload.get(key) is not None:
                candidates.append(payload[key])
        for value in candidates:
            try:
                context_window = int(value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
            if context_window > 0:
                return {
                    "context_window_tokens": context_window,
                    "context_profile_source": "ollama_show_model_info",
                }
        return {}

    # -------------------------------------------------------------------------
    def _show_payload(self, model: str) -> dict[str, Any] | None:
        normalized_model = model.strip()
        if normalized_model in self._show_payload_cache:
            return self._show_payload_cache[normalized_model]
        try:
            payload = self._post_json("/api/show", {"name": normalized_model})
        except Exception:
            payload = None
        self._show_payload_cache[normalized_model] = payload
        return payload

    # -------------------------------------------------------------------------
    def _show_capabilities(self, model: str) -> set[str] | None:
        payload = self._show_payload(model)
        if payload is None:
            return None
        raw = payload.get("capabilities")
        if not is_json_array(raw):
            return None
        return {str(item).strip().lower() for item in raw if str(item).strip()}

    # -------------------------------------------------------------------------
    def _probe_tool_support(self, model: str) -> bool | None:
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
                    "content": OLLAMA_TOOL_CAPABILITY_PROBE_PROMPT,
                }
            ],
            "stream": False,
            "tools": [self.tool_to_ollama_schema(tool)],
            "options": {"temperature": 0},
        }
        supported: bool | None = None
        try:
            response = self._post_json("/api/chat", payload)
            message = response.get("message") if is_json_object(response) else None
            supported = True
            source = "ollama_tool_request_accepted"
            if is_json_object(message) and self._parse_tool_calls(message):
                source = "ollama_probe"
        except HTTPError as exc:
            if self._is_explicit_tool_unsupported_error(exc):
                supported = False
                source = "ollama_tool_request_rejected"
            else:
                source = "ollama_probe"
        except Exception:
            source = "ollama_probe"
        if supported is not None:
            self.tool_capability_cache.set(
                self.base_url,
                model,
                supported,
                source=source,
            )
        return supported

    # -------------------------------------------------------------------------
    def _tool_support_source(self, model: str) -> str:
        return self.tool_capability_cache.source(self.base_url, model) or "unknown"

    # -------------------------------------------------------------------------
    @staticmethod
    def _is_explicit_tool_unsupported_error(exc: HTTPError) -> bool:
        try:
            body = exc.read().decode("utf-8", errors="ignore")
        except Exception:
            body = ""
        text = f"{exc.reason} {body}".lower()
        if "tool" not in text and "function" not in text:
            return False
        return any(
            marker in text
            for marker in (
                "not support",
                "unsupported",
                "does not support",
                "doesn't support",
                "no support",
            )
        )

    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    def pull_model(self, *, model: str) -> dict[str, Any]:
        return self._post_json("/api/pull", {"name": model, "stream": False})

    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    @staticmethod
    def _parse_tool_calls(message: dict[str, Any]) -> list[LLMToolCall]:
        calls: list[LLMToolCall] = []
        for item in json_array(message.get("tool_calls")):
            item = json_object(item)
            if not item:
                continue
            function = json_object(item.get("function"))
            calls.append(
                LLMToolCall(
                    id=item.get("id"),
                    name=str(function.get("name") or item.get("name") or ""),
                    arguments=json_object(function.get("arguments")),
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
        usage = compute_context_usage(
            effective_request, provider=self.provider_name
        )
        try:
            self._validate_request_capabilities(effective_request)
        except LLMStructuredOutputError as exc:
            exc.context_usage = usage.to_dict()
            raise
        payload: dict[str, Any] = {
            "model": effective_request.model,
            "messages": effective_request.messages,
            "stream": False,
            "options": {"temperature": effective_request.temperature},
        }
        if usage.selected_context_window is not None:
            payload["options"]["num_ctx"] = usage.selected_context_window
        if native_tools:
            payload["tools"] = [
                self.tool_to_ollama_schema(tool) for tool in native_tools
            ]
        if schema:
            payload["format"] = schema
        try:
            response = self._post_json_for_request(
                "/api/chat",
                payload,
                effective_request,
            )
        except LLMStructuredOutputError:
            raise
        except Exception as exc:
            raise LLMProviderRequestError.from_exception(
                exc,
                provider=self.provider_name,
                model=effective_request.model,
                stage="chat",
                context_usage=usage.to_dict(),
            ) from exc
        usage = apply_reported_usage(usage, response)
        message = json_object(response.get("message"))
        return LLMResult(
            content=str(message.get("content") or ""),
            raw=response,
            tool_calls=self._parse_tool_calls(message),
            finish_reason=str(response.get("done_reason") or "") or None,
            context_usage=usage.to_dict(),
        )

    # -------------------------------------------------------------------------
    def stream_chat(self, request: LLMRequest) -> Iterable[str]:
        request = prepare_request(request, provider=self.provider_name)
        usage = compute_context_usage(request, provider=self.provider_name)
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": request.messages,
            "stream": True,
            "options": {"temperature": request.temperature},
        }
        if usage.selected_context_window is not None:
            payload["options"]["num_ctx"] = usage.selected_context_window
        stream: LLMTextStream

        def iterate() -> Iterable[str]:
            nonlocal usage
            try:
                for event in self._stream_post_for_request("/api/chat", payload, request):
                    message = (
                        event.get("message")
                        if is_json_object(event.get("message"))
                        else None
                    )
                    if message is not None:
                        content = message.get("content")
                        if isinstance(content, str) and content:
                            yield content
                    if event.get("done"):
                        usage = apply_reported_usage(usage, event)
                        stream.context_usage = usage.to_dict()
                        break
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
        schema_json = (
            json_object(model_json_schema()) if callable(model_json_schema) else {}
        )
        effective_request = prepare_request(
            replace(request, response_json_schema=schema_json),
            provider=self.provider_name,
        )
        usage = compute_context_usage(effective_request, provider=self.provider_name)
        try:
            self._validate_request_capabilities(effective_request)
        except LLMStructuredOutputError as exc:
            exc.context_usage = usage.to_dict()
            raise
        payload: dict[str, Any] = {
            "model": effective_request.model,
            "messages": effective_request.messages,
            "stream": False,
            "format": schema_json,
            "think": False,
            "options": {"temperature": effective_request.temperature},
        }
        if usage.selected_context_window is not None:
            payload["options"]["num_ctx"] = usage.selected_context_window
        try:
            response = self._post_json_for_request(
                "/api/chat",
                payload,
                effective_request,
            )
        except LLMStructuredOutputError:
            raise
        except Exception as exc:
            raise LLMProviderRequestError.from_exception(
                exc,
                provider=self.provider_name,
                model=effective_request.model,
                stage="structured_output",
                context_usage=usage.to_dict(),
            ) from exc
        usage = apply_reported_usage(usage, response)
        message = json_object(response.get("message"))
        content = str(message.get("content") or "{}")
        try:
            loaded = json.loads(content)
        except (TypeError, json.JSONDecodeError) as exc:
            raise LLMResponseParsingError(
                provider=self.provider_name,
                model=effective_request.model,
                stage="structured_output",
                detail="The provider returned invalid JSON for structured extraction.",
                context_usage=usage.to_dict(),
            ) from exc
        if not is_json_object(loaded):
            raise LLMResponseParsingError(
                provider=self.provider_name,
                model=effective_request.model,
                stage="structured_output",
                detail="The provider returned a JSON value instead of an object.",
                context_usage=usage.to_dict(),
            )
        validator = getattr(schema, "model_validate", None)
        if callable(validator):
            try:
                validated = validator(loaded)
            except Exception as exc:  # noqa: BLE001
                raise LLMResponseParsingError(
                    provider=self.provider_name,
                    model=effective_request.model,
                    stage="structured_output",
                    detail="The provider response did not match the requested extraction schema.",
                    context_usage=usage.to_dict(),
                ) from exc
            dumper = getattr(validated, "model_dump", None)
            if callable(dumper):
                return LLMStructuredOutput(
                    json_object(dumper(mode="json")),
                    context_usage=usage.to_dict(),
                )
        return LLMStructuredOutput(loaded, context_usage=usage.to_dict())

    # -------------------------------------------------------------------------
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
        if not is_json_array(embedding):
            return []
        return [float(value) for value in embedding if isinstance(value, (int | float))]

    # -------------------------------------------------------------------------
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
