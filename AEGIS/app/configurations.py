from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Literal

from DILIGENT.app.constants import CLOUD_MODEL_CHOICES

from AEGIS.app.constants import SETUP_DIR

CONFIGURATION_CACHE: dict[str, Any] | None = None
CONFIGURATION_FILE = os.path.join(SETUP_DIR, "configurations.json")

###############################################################################
DEFAULT_CONFIGURATION: dict[str, Any] = {
    "ollama_host_default": "http://localhost:11434",    
    "client_defaults": {
        "default_agent_model": "qwen3:8b",
        "default_clinical_model": "gpt-oss:20b",
        "default_cloud_provider": "openai",
        "default_cloud_model": "gpt-4.1-mini",
        "default_cloud_embedding_model": "text-embedding-3-large",
        "default_use_cloud_services": False,
        "default_ollama_temperature": 0.7,
        "default_ollama_reasoning": False,
    },
    "external_data": {
        "default_llm_timeout_seconds": 3600.0,
        "llm_null_match_names": [
            "",
            "none",
            "no match",
            "no matches",
            "not found",
            "unknown",
            "not applicable",
            "n a",
        ],
    },
    "geographics": {
        "filter_choices": [
            "Natural Color",
            "Topographic",
            "Population Density",
            "Weather Overlay",
        ],
        "default_filter": "Natural Color",
        "openai_model_choices": [
            "gpt-4o-mini",
            "gpt-4.1",
            "gpt-4.1-mini",
            "gpt-3.5-turbo",
        ],
        "agent_model_choices": ["llama3", "mistral", "phi3"],
        "default_agent_model": "llama3",
        "default_use_cloud": False,
        "default_agentic_temperature": 0.7,
        "min_agentic_temperature": 0.0,
        "max_agentic_temperature": 2.0,
    },
}

###############################################################################
def load_configuration_file() -> dict[str, Any]:
    if os.path.exists(CONFIGURATION_FILE):
        try:
            with open(CONFIGURATION_FILE, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Unable to load configuration from {CONFIGURATION_FILE}"
            ) from exc
    return json.loads(json.dumps(DEFAULT_CONFIGURATION))

# -----------------------------------------------------------------------------
def get_nested_value(data: dict[str, Any], *keys: str, default: Any | None = None) -> Any:
    current: Any = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    return current

###############################################################################
CONFIGURATION_DATA = load_configuration_file()

# -----------------------------------------------------------------------------
def get_configuration() -> dict[str, Any]:
    return CONFIGURATION_DATA

# -----------------------------------------------------------------------------
def get_configuration_value(*keys: str, default: Any | None = None) -> Any:
    return get_nested_value(CONFIGURATION_DATA, *keys, default=default)

###############################################################################
CLIENT_DEFAULTS = get_configuration_value("client_defaults", default={})
DEFAULT_AGENT_MODEL = CLIENT_DEFAULTS.get("default_agent_model", "")
DEFAULT_CLOUD_PROVIDER = CLIENT_DEFAULTS.get("default_cloud_provider", "")
DEFAULT_CLOUD_MODEL = CLIENT_DEFAULTS.get("default_cloud_model", "")
DEFAULT_CLOUD_EMBEDDING_MODEL = CLIENT_DEFAULTS.get(
    "default_cloud_embedding_model", ""
)
DEFAULT_USE_CLOUD_SERVICES = CLIENT_DEFAULTS.get("default_use_cloud_services", False)
DEFAULT_OLLAMA_TEMPERATURE = CLIENT_DEFAULTS.get("default_ollama_temperature", 0.7)
DEFAULT_OLLAMA_REASONING = CLIENT_DEFAULTS.get("default_ollama_reasoning", False)

cloud_models = CLOUD_MODEL_CHOICES.get(DEFAULT_CLOUD_PROVIDER, [])
if DEFAULT_CLOUD_MODEL not in cloud_models:
    DEFAULT_CLOUD_MODEL = cloud_models[0] if cloud_models else ""

OLLAMA_HOST_DEFAULT = get_configuration_value("ollama_host_default", default="")

EXTERNAL_DATA_CONFIGURATION = get_configuration_value("external_data", default={})
DEFAULT_LLM_TIMEOUT_SECONDS = EXTERNAL_DATA_CONFIGURATION.get(
    "default_llm_timeout_seconds", 3600.0
)

GEOGRAPHICS_CONFIGURATION = get_configuration_value("geographics", default={})
GEOGRAPHICS_FILTER_CHOICES = list(GEOGRAPHICS_CONFIGURATION.get("filter_choices", []))
GEOGRAPHICS_DEFAULT_FILTER = GEOGRAPHICS_CONFIGURATION.get("default_filter", "")
GEOGRAPHICS_OPENAI_MODEL_CHOICES = list(
    GEOGRAPHICS_CONFIGURATION.get("openai_model_choices", [])
)
GEOGRAPHICS_AGENT_MODEL_CHOICES = list(
    GEOGRAPHICS_CONFIGURATION.get("agent_model_choices", [])
)
GEOGRAPHICS_DEFAULT_AGENT_MODEL = GEOGRAPHICS_CONFIGURATION.get(
    "default_agent_model", ""
)
GEOGRAPHICS_DEFAULT_USE_CLOUD = GEOGRAPHICS_CONFIGURATION.get(
    "default_use_cloud", False
)
GEOGRAPHICS_DEFAULT_AGENTIC_TEMPERATURE = GEOGRAPHICS_CONFIGURATION.get(
    "default_agentic_temperature", 0.7
)
GEOGRAPHICS_MIN_AGENTIC_TEMPERATURE = GEOGRAPHICS_CONFIGURATION.get(
    "min_agentic_temperature", 0.0
)
GEOGRAPHICS_MAX_AGENTIC_TEMPERATURE = GEOGRAPHICS_CONFIGURATION.get(
    "max_agentic_temperature", 2.0
)


###############################################################################
@dataclass
class ClientRuntimeConfig:
    filter_choices: list[str]
    default_filter: str
    openai_model_choices: list[str]
    agent_model_choices: list[str]
    default_agent_model: str
    default_use_cloud: bool
    agentic_temperature_default: float
    agentic_temperature_min: float
    agentic_temperature_max: float

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
        cls.llm_provider = DEFAULT_CLOUD_PROVIDER
        cls.cloud_model = DEFAULT_CLOUD_MODEL
        cls.use_cloud_services = DEFAULT_USE_CLOUD_SERVICES
        cls.ollama_temperature = DEFAULT_OLLAMA_TEMPERATURE
        cls.ollama_reasoning = DEFAULT_OLLAMA_REASONING
        cls.revision = 0

    # -------------------------------------------------------------------------
    @classmethod
    def get_revision(cls) -> int:
        return cls.revision

    # -------------------------------------------------------------------------
    @classmethod
    def resolve_provider_and_model(
        cls, _: Literal["agent"]
    ) -> tuple[str, str]:
        if cls.is_cloud_enabled():
            provider = cls.get_llm_provider()
            model = cls.get_cloud_model().strip()            
        else:
            provider = "ollama"
            model = cls.get_agent_model().strip()   
            
        return provider, model.strip()

