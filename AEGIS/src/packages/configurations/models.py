from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from AEGIS.src.packages.constants import AGENT_MODEL_CHOICES, CLOUD_MODEL_CHOICES
from AEGIS.src.packages.types import coerce_bool, coerce_float, coerce_str


###############################################################################
@dataclass(frozen=True)
class LLMRuntimeDefaults:
    agent_model: str
    llm_provider: str
    cloud_model: str
    use_cloud_services: bool
    ollama_temperature: float
    ollama_reasoning: bool


###############################################################################
def build_llm_runtime_defaults(data: dict[str, Any]) -> LLMRuntimeDefaults:
    agent_default = AGENT_MODEL_CHOICES[0] if AGENT_MODEL_CHOICES else ""
    provider_default = coerce_str(data.get("llm_provider"), "openai").lower()
    provider_models = CLOUD_MODEL_CHOICES.get(provider_default, [])
    cloud_default = provider_models[0] if provider_models else ""

    return LLMRuntimeDefaults(
        agent_model=coerce_str(data.get("agent_model"), agent_default),
        llm_provider=provider_default,
        cloud_model=coerce_str(data.get("cloud_model"), cloud_default),
        use_cloud_services=coerce_bool(data.get("use_cloud_services"), False),
        ollama_temperature=coerce_float(data.get("ollama_temperature"), 0.7),
        ollama_reasoning=coerce_bool(data.get("ollama_reasoning"), False),
    )
