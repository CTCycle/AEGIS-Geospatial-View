from __future__ import annotations

from typing import Any, cast

import httpx

from server.services.llm.deepseek_provider import DeepSeekProvider
from server.services.llm.types import ModelDescriptor

###############################################################################
OPENCODE_PROVIDER = "opencode"
OPENCODE_GO_PROVIDER = "opencode-go"

DEFAULT_OPENCODE_BASE_URL = "https://opencode.ai/zen/v1"
DEFAULT_OPENCODE_GO_BASE_URL = "https://opencode.ai/zen/go/v1"

OPENCODE_COMPATIBLE_MODELS: dict[str, frozenset[str]] = {
    OPENCODE_PROVIDER: frozenset(
        {
            "grok-4.5", "grok-build-0.1", "deepseek-v4-pro", "deepseek-v4-flash",
            "minimax-m3", "minimax-m2.7", "minimax-m2.5", "glm-5.2", "glm-5.1",
            "glm-5", "kimi-k2.5", "kimi-k2.6", "kimi-k2.7-code", "kimi-k3",
            "big-pickle", "mimo-v2.5-free", "laguna-s-2.1-free",
            "ling-3.0-flash-free", "north-mini-code-free", "nemotron-3-ultra-free",
            "deepseek-v4-flash-free",
        }
    ),
    OPENCODE_GO_PROVIDER: frozenset(
        {
            "grok-4.5", "glm-5.2", "glm-5.1", "kimi-k3", "kimi-k2.7-code",
            "kimi-k2.6", "deepseek-v4-pro", "deepseek-v4-flash", "mimo-v2.5",
            "mimo-v2.5-pro", "hy3",
        }
    ),
}

OPENCODE_BASE_URLS = {
    OPENCODE_PROVIDER: DEFAULT_OPENCODE_BASE_URL,
    OPENCODE_GO_PROVIDER: DEFAULT_OPENCODE_GO_BASE_URL,
}

###############################################################################
class OpenCodeProvider(DeepSeekProvider):
    """OpenCode Go/Zen adapter for their OpenAI-compatible model subset."""

    provider_name = OPENCODE_PROVIDER

    # -------------------------------------------------------------------------
    def __init__(self, *, api_key: str, provider_name: str) -> None:
        if provider_name not in OPENCODE_BASE_URLS:
            raise ValueError(f"Unsupported OpenCode provider '{provider_name}'.")
        super().__init__(api_key=api_key, base_url=OPENCODE_BASE_URLS[provider_name])
        self.provider_name = provider_name

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
        payload = cast(object, response.json())
        if not isinstance(payload, dict):
            return []
        typed_payload = cast(dict[str, Any], payload)
        raw_entries = typed_payload.get("data", [])
        entries = cast(list[object], raw_entries) if isinstance(raw_entries, list) else []
        compatible = OPENCODE_COMPATIBLE_MODELS[self.provider_name]
        models: list[ModelDescriptor] = []
        for raw_item in entries:
            if not isinstance(raw_item, dict):
                continue
            item = cast(dict[str, Any], raw_item)
            if str(item.get("id") or "").strip() in compatible:
                models.append(self._model_descriptor(item))
        return models

    # -------------------------------------------------------------------------
    def _capabilities_for_model(self, model: str) -> set[str]:
        if model.strip().lower() in OPENCODE_COMPATIBLE_MODELS[self.provider_name]:
            return {"chat", "stream", "structured", "structured_output", "tools"}
        return {"chat", "stream"}

    # -------------------------------------------------------------------------
    def _model_descriptor(self, item: dict[str, Any]) -> ModelDescriptor:
        model_id = str(item.get("id") or "").strip()
        return ModelDescriptor(
            name=model_id,
            description=self._description_for_model(model_id),
            provider=self.provider_name,
            capabilities=sorted(self._capabilities_for_model(model_id)),
            metadata={
                "family": model_id.split("-")[0] if "-" in model_id else model_id,
                "owned_by": str(item.get("owned_by") or "opencode"),
                "protocol": "openai-chat-completions",
                "tool_support_source": "provider",
            },
        )

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
