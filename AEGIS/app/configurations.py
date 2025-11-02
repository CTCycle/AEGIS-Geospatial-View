from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Literal

from AEGIS.app.constants import CLOUD_MODEL_CHOICES, AGENT_MODEL_CHOICES

from AEGIS.app.constants import SETUP_DIR

CONFIGURATION_CACHE: dict[str, Any] | None = None
CONFIGURATION_FILE = os.path.join(SETUP_DIR, "configurations.json")


###############################################################################
def load_configuration_file() -> dict[str, Any] | None:
    if os.path.exists(CONFIGURATION_FILE):
        try:
            with open(CONFIGURATION_FILE, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Unable to load configuration from {CONFIGURATION_FILE}"
            ) from exc


# -----------------------------------------------------------------------------
def get_nested_value(
    data: dict[str, Any], *keys: str, default: Any | None = None
) -> Any:
    current: Any = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    return current


# -----------------------------------------------------------------------------
CONFIGURATION_DATA = load_configuration_file()


def get_configuration_value(*keys: str, default: Any | None = None) -> Any:
    configuration = CONFIGURATION_DATA if CONFIGURATION_DATA is not None else {}
    return get_nested_value(configuration, *keys, default=default)


###############################################################################
DEFAULT_AGENT_MODEL = AGENT_MODEL_CHOICES[0]
DEFAULT_CLOUD_PROVIDER = CLOUD_MODEL_CHOICES["openai"]
DEFAULT_CLOUD_MODEL = CLOUD_MODEL_CHOICES["openai"][0]

DEFAULT_CLOUD_EMBEDDING_MODEL = ""
DEFAULT_OLLAMA_TEMPERATURE = 0.7
DEFAULT_OLLAMA_REASONING = False

OLLAMA_HOST_DEFAULT = get_configuration_value("ollama_host_default", default="")
DEFAULT_LLM_TIMEOUT_SECONDS = CONFIGURATION_DATA.get(
    "default_llm_timeout_seconds", 3600.0
)


###############################################################################
@dataclass
class ClientRuntimeConfig:
    agent_model: str = DEFAULT_AGENT_MODEL
    llm_provider: str = "openai"
    cloud_model: str = DEFAULT_CLOUD_MODEL
    use_cloud_services: bool = False
    ollama_temperature: float = DEFAULT_OLLAMA_TEMPERATURE
    ollama_reasoning: bool = DEFAULT_OLLAMA_REASONING
    revision: int = 0

    # -------------------------------------------------------------------------
    @classmethod
    def touch_revision(cls) -> None:
        cls.revision += 1

    # -------------------------------------------------------------------------
    @classmethod
    def set_agent_model(cls, model: str) -> str:
        value = model.strip()
        if value and value != cls.agent_model:
            cls.agent_model = value
            cls.touch_revision()
        return cls.agent_model

    # -------------------------------------------------------------------------
    @classmethod
    def set_llm_provider(cls, provider: str) -> str:
        value = provider.strip()
        if value and value != cls.llm_provider:
            cls.llm_provider = value
            models = CLOUD_MODEL_CHOICES.get(cls.llm_provider, [])
            if cls.cloud_model not in models:
                cls.cloud_model = models[0] if models else ""
            cls.touch_revision()
        return cls.llm_provider

    # -------------------------------------------------------------------------
    @classmethod
    def set_cloud_model(cls, model: str) -> str:
        value = model.strip()
        if not value:
            if cls.cloud_model:
                cls.cloud_model = ""
                cls.touch_revision()
            return cls.cloud_model
        models = CLOUD_MODEL_CHOICES.get(cls.llm_provider, [])
        if value not in models:
            if models and cls.cloud_model != models[0]:
                cls.cloud_model = models[0]
                cls.touch_revision()
            return cls.cloud_model
        if cls.cloud_model != value:
            cls.cloud_model = value
            cls.touch_revision()
        return cls.cloud_model

    # -------------------------------------------------------------------------
    @classmethod
    def set_use_cloud_services(cls, enabled: bool) -> bool:
        normalized = bool(enabled)
        if cls.use_cloud_services != normalized:
            cls.use_cloud_services = normalized
            cls.touch_revision()
        return cls.use_cloud_services

    # -------------------------------------------------------------------------
    @classmethod
    def set_ollama_temperature(cls, value: float | None) -> float:
        try:
            parsed = float(value) if value is not None else cls.ollama_temperature
        except (TypeError, ValueError):
            parsed = cls.ollama_temperature
        parsed = max(0.0, min(2.0, parsed))
        rounded = round(parsed, 2)
        if cls.ollama_temperature != rounded:
            cls.ollama_temperature = rounded
            cls.touch_revision()
        return cls.ollama_temperature

    # -------------------------------------------------------------------------
    @classmethod
    def set_ollama_reasoning(cls, enabled: bool) -> bool:
        normalized = bool(enabled)
        if cls.ollama_reasoning != normalized:
            cls.ollama_reasoning = normalized
            cls.touch_revision()
        return cls.ollama_reasoning

    # -------------------------------------------------------------------------
    @classmethod
    def get_agent_model(cls) -> str:
        return cls.agent_model

    # -------------------------------------------------------------------------
    @classmethod
    def get_llm_provider(cls) -> str:
        return cls.llm_provider

    # -------------------------------------------------------------------------
    @classmethod
    def get_cloud_model(cls) -> str:
        return cls.cloud_model

    # -------------------------------------------------------------------------
    @classmethod
    def is_cloud_enabled(cls) -> bool:
        return cls.use_cloud_services

    # -------------------------------------------------------------------------
    @classmethod
    def get_ollama_temperature(cls) -> float:
        return cls.ollama_temperature

    # -------------------------------------------------------------------------
    @classmethod
    def is_ollama_reasoning_enabled(cls) -> bool:
        return cls.ollama_reasoning

    # -------------------------------------------------------------------------
    @classmethod
    def reset_defaults(cls) -> None:
        cls.agent_model = DEFAULT_AGENT_MODEL
        cls.llm_provider = "openai"
        cls.cloud_model = DEFAULT_CLOUD_MODEL
        cls.use_cloud_services = False
        cls.ollama_temperature = DEFAULT_OLLAMA_TEMPERATURE
        cls.ollama_reasoning = DEFAULT_OLLAMA_REASONING
        cls.revision = 0

    # -------------------------------------------------------------------------
    @classmethod
    def get_revision(cls) -> int:
        return cls.revision

    # -------------------------------------------------------------------------
    @classmethod
    def resolve_provider_and_model(cls, purpose: Literal["agent"]) -> tuple[str, str]:
        if cls.is_cloud_enabled():
            provider = cls.get_llm_provider()
            model = cls.get_cloud_model().strip()
            if not model:
                model = cls.get_agent_model()
        else:
            provider = "ollama"
            model = cls.get_agent_model()

        return provider, model.strip()
