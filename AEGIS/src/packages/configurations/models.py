from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from AEGIS.src.packages.configurations.base import ensure_mapping
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
    payload = ensure_mapping(data)
    provider_fallback = "openai" 
    provider_value = coerce_str(payload.get("llm_provider"), provider_fallback).lower()
    provider = provider_value if provider_value in CLOUD_MODEL_CHOICES else provider_fallback
    provider_models = CLOUD_MODEL_CHOICES.get(provider, [])
    cloud_fallback = provider_models[0] if provider_models else ""
    agent_fallback = AGENT_MODEL_CHOICES[0] if AGENT_MODEL_CHOICES else ""
    agent_model = coerce_str(payload.get("agent_model"), agent_fallback)
    if agent_model not in AGENT_MODEL_CHOICES:
        agent_model = agent_fallback
    cloud_model = coerce_str(payload.get("cloud_model"), cloud_fallback)
    if cloud_model not in provider_models:
        cloud_model = cloud_fallback

    return LLMRuntimeDefaults(
        agent_model=agent_model,
        llm_provider=provider,
        cloud_model=cloud_model,
        use_cloud_services=coerce_bool(payload.get("use_cloud_services"), False),
        ollama_temperature=coerce_float(payload.get("ollama_temperature"), 0.7),
        ollama_reasoning=coerce_bool(payload.get("ollama_reasoning"), False),
    )
