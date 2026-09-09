from __future__ import annotations

from server.common.typing import is_json_array, is_json_object

from dataclasses import replace
from typing import Any

import httpx

from server.common.constants import AEGIS_VERSION
from server.services.llm.deepseek_provider import DeepSeekProvider
from server.services.llm.errors import LLMProviderRequestError
from server.services.llm.openai_provider import OpenAIProvider
from server.services.llm.types import LLMRequest, ModelDescriptor

###############################################################################
OPENCODE_PROVIDER = "opencode"
OPENCODE_GO_PROVIDER = "opencode-go"

DEFAULT_OPENCODE_BASE_URL = "https://opencode.ai/zen/v1"
DEFAULT_OPENCODE_GO_BASE_URL = "https://opencode.ai/zen/go/v1"

OPENAI_CHAT_PROTOCOL = "openai-chat-completions"
OPENAI_RESPONSES_PROTOCOL = "openai-responses"
ANTHROPIC_MESSAGES_PROTOCOL = "anthropic-messages"
GOOGLE_MODEL_PROTOCOL = "google-model"
UNKNOWN_PROTOCOL = "unknown"

SUPPORTED_OPENCODE_PROTOCOLS = frozenset(
    {OPENAI_CHAT_PROTOCOL, OPENAI_RESPONSES_PROTOCOL}
)

# OpenCode's live /models response currently contains IDs and ownership but
# does not reliably carry the endpoint family. Keep the published endpoint
# table explicit instead of guessing from model names.
_ZEN_RESPONSES = {
    "gpt-6-astra", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna",
    "gpt-5.5", "gpt-5.5-pro", "gpt-5.4", "gpt-5.4-pro", "gpt-5.4-mini",
    "gpt-5.4-nano", "gpt-5.3-codex", "gpt-5.3-codex-spark", "gpt-5.2",
    "gpt-5.2-codex", "gpt-5.1", "gpt-5.1-codex", "gpt-5.1-codex-max",
    "gpt-5.1-codex-mini", "gpt-5", "gpt-5-codex", "gpt-5-nano",
    "grok-4.6", "grok-4.5", "grok-build-0.1", "muse-spark-1.3",
    "muse-spark-1.2", "muse-spark-1.3-contributor-free",
}

_ZEN_CHAT = {
    "deepseek-v4-pro", "deepseek-v4-flash", "deepseek-v4-flash-vision-exp",
    "minimax-m3", "minimax-m2.7", "minimax-m2.5", "glm-5.3-flash",
    "glm-5.3", "glm-5.2", "glm-5.1", "glm-5", "kimi-k2.5", "kimi-k2.6",
    "kimi-k2.7-code", "kimi-k3", "big-pickle", "mimo-v2.5-free",
    "ling-3.0-flash-fin-free", "nemotron-3-ultra-free",
    "nemotron-3.5-lightning-free",
}

_ZEN_MESSAGES = {
    "claude-fable-5-1", "claude-fable-5", "claude-opus-5", "claude-opus-4-8",
    "claude-opus-4-7", "claude-opus-4-6", "claude-opus-4-5", "claude-sonnet-5",
    "claude-sonnet-4-6", "claude-sonnet-4-5", "claude-haiku-4-5",
    "qwen3.7-max", "qwen3.7-plus", "qwen3.6-plus", "qwen3.5-plus",
}

_ZEN_GOOGLE = {
    "gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash",
    "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.1-pro",
    "gemini-3-flash",
}

_ZEN_GO_RESPONSES = {
    "grok-4.6", "gpt-5.6-luna", "muse-spark-1.3-contributor",
    "muse-spark-1.2-contributor",
}

_ZEN_GO_CHAT = {
    "glm-5.3-flash", "glm-5.3", "glm-5.2", "glm-5.1", "kimi-k3",
    "kimi-k2.7-code", "kimi-k2.6", "longcat-2.0", "deepseek-v4-pro",
    "deepseek-v4-flash", "deepseek-v4-flash-vision-exp", "mimo-v2.5",
    "mimo-v2.5-pro", "hy4-preview", "hy3", "omen-alpha",
}

_ZEN_GO_MESSAGES = {
    "minimax-m3", "minimax-m2.7", "minimax-m2.5", "qwen3.8-max",
    "qwen3.8-flash", "qwen3.7-max", "qwen3.7-plus", "qwen3.6-plus",
}

OPENCODE_PROTOCOL_REGISTRY: dict[str, dict[str, str]] = {
    OPENCODE_PROVIDER: {
        **{model: OPENAI_RESPONSES_PROTOCOL for model in _ZEN_RESPONSES},
        **{model: OPENAI_CHAT_PROTOCOL for model in _ZEN_CHAT},
        **{model: ANTHROPIC_MESSAGES_PROTOCOL for model in _ZEN_MESSAGES},
        **{model: GOOGLE_MODEL_PROTOCOL for model in _ZEN_GOOGLE},
    },
    OPENCODE_GO_PROVIDER: {
        **{model: OPENAI_RESPONSES_PROTOCOL for model in _ZEN_GO_RESPONSES},
        **{model: OPENAI_CHAT_PROTOCOL for model in _ZEN_GO_CHAT},
        **{model: ANTHROPIC_MESSAGES_PROTOCOL for model in _ZEN_GO_MESSAGES},
    },
}

OPENCODE_COMPATIBLE_MODELS: dict[str, frozenset[str]] = {
    provider: frozenset(
        model
        for model, protocol in registry.items()
        if protocol in SUPPORTED_OPENCODE_PROTOCOLS
    )
    for provider, registry in OPENCODE_PROTOCOL_REGISTRY.items()
}

OPENCODE_BASE_URLS = {
    OPENCODE_PROVIDER: DEFAULT_OPENCODE_BASE_URL,
    OPENCODE_GO_PROVIDER: DEFAULT_OPENCODE_GO_BASE_URL,
}

###############################################################################
class _OpenCodeResponsesTransport(OpenAIProvider):
    """OpenAI Responses serialization with OpenCode identity and headers."""

    def __init__(self, parent: "OpenCodeProvider") -> None:
        super().__init__(api_key=parent.api_key, base_url=parent.base_url)
        self.provider_name = parent.provider_name
        self._parent = parent

    # -------------------------------------------------------------------------
    def _request_headers(self, request: LLMRequest | None = None) -> dict[str, str]:
        return self._parent._request_headers(request)  # pyright: ignore[reportPrivateUsage]

    # -------------------------------------------------------------------------
    def list_models(self) -> list[ModelDescriptor]:
        return []

    # -------------------------------------------------------------------------
    def supports_tools(self, model: str) -> bool | None:
        _ = model
        return True

    # -------------------------------------------------------------------------
    def supports_structured_output(self, model: str) -> bool | None:
        _ = model
        return True

###############################################################################
class OpenCodeProvider(DeepSeekProvider):
    """OpenCode Go/Zen adapter for explicitly published endpoint families."""

    provider_name = OPENCODE_PROVIDER

    # -------------------------------------------------------------------------
    def __init__(self, *, api_key: str, provider_name: str) -> None:
        if provider_name not in OPENCODE_BASE_URLS:
            raise ValueError(f"Unsupported OpenCode provider '{provider_name}'.")
        super().__init__(api_key=api_key, base_url=OPENCODE_BASE_URLS[provider_name])
        self.provider_name = provider_name
        self._declared_model_protocols: dict[str, str] = {}
        self._responses_transport: _OpenCodeResponsesTransport | None = None

    # -------------------------------------------------------------------------
    def _request_headers(self, request: LLMRequest | None = None) -> dict[str, str]:
        headers = {"User-Agent": f"AEGIS-Geospatial-View/{AEGIS_VERSION}"}
        if request is None:
            return headers
        session_id = (request.provider_session_id or "").strip()
        if not session_id:
            raise LLMProviderRequestError(
                provider=self.provider_name,
                model=request.model,
                stage="request_headers",
                code="provider_session_required",
                retryable=False,
            )
        headers["x-opencode-session"] = session_id
        return headers

    # -------------------------------------------------------------------------
    def _responses(self) -> _OpenCodeResponsesTransport:
        if self._responses_transport is None:
            self._responses_transport = _OpenCodeResponsesTransport(self)
        return self._responses_transport

    # -------------------------------------------------------------------------
    def protocol_for_model(self, model: str) -> str:
        normalized = model.strip().lower()
        declared = self._declared_model_protocols.get(normalized)
        if declared is not None:
            return declared
        return OPENCODE_PROTOCOL_REGISTRY[self.provider_name].get(
            normalized, UNKNOWN_PROTOCOL
        )

    # -------------------------------------------------------------------------
    def _require_supported_protocol(self, request: LLMRequest) -> str:
        protocol = self.protocol_for_model(request.model)
        if protocol in SUPPORTED_OPENCODE_PROTOCOLS:
            return protocol
        raise LLMProviderRequestError(
            provider=self.provider_name,
            model=request.model,
            stage="request_validation",
            code="provider_transport_unsupported",
            retryable=False,
        )

    # -------------------------------------------------------------------------
    def _responses_request(self, request: LLMRequest) -> LLMRequest:
        metadata = {
            **request.metadata,
            "protocol": OPENAI_RESPONSES_PROTOCOL,
            # OpenCode's Responses-backed GPT/Grok models follow the reasoning
            # model contract; omit unsupported sampling parameters.
            "supports_temperature": False,
        }
        return replace(request, provider=self.provider_name, metadata=metadata)

    # -------------------------------------------------------------------------
    def supports_tools(self, model: str) -> bool | None:
        if self.protocol_for_model(model) not in SUPPORTED_OPENCODE_PROTOCOLS:
            return False
        declared = self._declared_model_capabilities.get(
            model.strip().lower(), {}
        ).get("supports_tools")
        return declared if isinstance(declared, bool) else True

    # -------------------------------------------------------------------------
    def supports_structured_output(self, model: str) -> bool | None:
        if self.protocol_for_model(model) not in SUPPORTED_OPENCODE_PROTOCOLS:
            return False
        declared = self._declared_model_capabilities.get(
            model.strip().lower(), {}
        ).get("supports_structured_output")
        return declared if isinstance(declared, bool) else True

    # -------------------------------------------------------------------------
    def list_models(self) -> list[ModelDescriptor]:
        response = httpx.get(
            f"{self.base_url}/models",
            headers={
                **self._request_headers(),
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
            },
            timeout=5.0,
        )
        response.raise_for_status()
        payload = response.json()
        if not is_json_object(payload):
            return []
        raw_entries = payload.get("data", [])
        entries = raw_entries if is_json_array(raw_entries) else []
        models: list[ModelDescriptor] = []
        for raw_item in entries:
            if not is_json_object(raw_item):
                continue
            if str(raw_item.get("id") or "").strip():
                models.append(self._model_descriptor(raw_item))
        for model in models:
            declared = {
                key: value
                for key, value in model.metadata.items()
                if key in {"supports_tools", "supports_structured_output"}
                and isinstance(value, bool)
            }
            if declared:
                self._declared_model_capabilities[model.name.lower()] = declared
            protocol = model.metadata.get("protocol")
            if isinstance(protocol, str):
                self._declared_model_protocols[model.name.lower()] = protocol
        return models

    # -------------------------------------------------------------------------
    def _model_descriptor(self, item: dict[str, Any]) -> ModelDescriptor:
        model_id = str(item.get("id") or "").strip()
        protocol = OPENCODE_PROTOCOL_REGISTRY[self.provider_name].get(
            model_id.lower(), UNKNOWN_PROTOCOL
        )
        supported = protocol in SUPPORTED_OPENCODE_PROTOCOLS
        metadata: dict[str, Any] = {
            "family": model_id.split("-")[0] if "-" in model_id else model_id,
            "owned_by": str(item.get("owned_by") or "opencode"),
            "protocol": protocol,
            "protocol_source": "opencode_published_endpoint_table",
            "tool_support_source": "provider_protocol_registry",
        }
        if not supported:
            metadata["supports_tools"] = False
            metadata["supports_structured_output"] = False
            metadata["agent_selection_disabled_reason"] = (
                "This OpenCode model uses an unsupported transport. "
                "AEGIS supports Chat Completions and Responses only."
                if protocol != UNKNOWN_PROTOCOL
                else "OpenCode did not publish a supported transport for this model."
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
            if supported:
                metadata["supports_tools"] = "tools" in normalized
                metadata["supports_structured_output"] = bool(
                    {"structured", "structured_output"} & normalized
                )
            capabilities = sorted(normalized)
        elif supported:
            capabilities = [
                "chat",
                "stream",
                "structured",
                "structured_output",
                "tools",
            ]
        else:
            capabilities = ["chat", "stream"]
        return ModelDescriptor(
            name=model_id,
            description=self._description_for_model(model_id),
            provider=self.provider_name,
            capabilities=capabilities,
            metadata=metadata,
        )

    # -------------------------------------------------------------------------
    def chat(self, request: LLMRequest, **kwargs: Any):  # type: ignore[no-untyped-def]
        protocol = self._require_supported_protocol(request)
        if protocol == OPENAI_RESPONSES_PROTOCOL:
            return self._responses().chat(self._responses_request(request), **kwargs)
        return super().chat(request, **kwargs)

    # -------------------------------------------------------------------------
    async def achat(self, request: LLMRequest, **kwargs: Any):  # type: ignore[no-untyped-def]
        protocol = self._require_supported_protocol(request)
        if protocol == OPENAI_RESPONSES_PROTOCOL:
            return await self._responses().achat(
                self._responses_request(request), **kwargs
            )
        return await super().achat(request, **kwargs)

    # -------------------------------------------------------------------------
    def stream_chat(self, request: LLMRequest):  # type: ignore[no-untyped-def]
        protocol = self._require_supported_protocol(request)
        if protocol == OPENAI_RESPONSES_PROTOCOL:
            return self._responses().stream_chat(self._responses_request(request))
        return super().stream_chat(request)

    # -------------------------------------------------------------------------
    def structured_output(self, request: LLMRequest, schema: type[Any]):
        protocol = self._require_supported_protocol(request)
        if protocol == OPENAI_RESPONSES_PROTOCOL:
            return self._responses().structured_output(
                self._responses_request(request), schema
            )
        return super().structured_output(request, schema)

    # -------------------------------------------------------------------------
    async def astructured_output(self, request: LLMRequest, schema: type[Any]):
        protocol = self._require_supported_protocol(request)
        if protocol == OPENAI_RESPONSES_PROTOCOL:
            return await self._responses().astructured_output(
                self._responses_request(request), schema
            )
        return await super().astructured_output(request, schema)

    # -------------------------------------------------------------------------
    @staticmethod
    def _description_for_model(model_id: str) -> str:
        normalized = model_id.lower()
        if normalized.startswith("deepseek"):
            return "OpenCode model for reasoning, planning, coding, and tool-driven workflows."
        if normalized.startswith("grok") or normalized.startswith("glm"):
            return "OpenCode model for fast interactive agent and coding workflows."
        if normalized.startswith("kimi") or normalized.startswith("qwen"):
            return "OpenCode model for long-context planning and coding workflows."
        return "OpenCode model available for AEGIS agent duties and tool-driven chat."
