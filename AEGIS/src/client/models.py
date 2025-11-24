from __future__ import annotations

from dataclasses import dataclass

from AEGIS.src.packages.configurations import LLMRuntimeDefaults
from AEGIS.src.packages.constants import AGENT_MODEL_CHOICES, CLOUD_MODEL_CHOICES


###############################################################################
@dataclass
class LLMRuntimeState:
    defaults: LLMRuntimeDefaults
    agent_model: str = ""
    llm_provider: str = ""
    cloud_model: str = ""
    use_cloud_services: bool = False
    ollama_temperature: float = 0.0
    ollama_reasoning: bool = False
    revision: int = 0

    # -------------------------------------------------------------------------
    def __post_init__(self) -> None:
        self.reset_defaults()

    # -------------------------------------------------------------------------
    def touch_revision(self) -> None:
        self.revision += 1

    # -------------------------------------------------------------------------
    def reset_defaults(self) -> None:
        d = self.defaults
        self.agent_model = d.agent_model
        self.llm_provider = d.llm_provider
        self.cloud_model = d.cloud_model
        self.use_cloud_services = d.use_cloud_services
        self.ollama_temperature = d.ollama_temperature
        self.ollama_reasoning = d.ollama_reasoning
        self.touch_revision()

    # -------------------------------------------------------------------------
    def is_cloud_enabled(self) -> bool:
        return self.use_cloud_services

    # -------------------------------------------------------------------------
    def set_cloud_enabled(self, enabled: bool) -> bool:
        normalized = bool(enabled)
        if normalized != self.use_cloud_services:
            self.use_cloud_services = normalized
            self.touch_revision()
        return self.use_cloud_services

    # -------------------------------------------------------------------------
    def set_agent_model(self, model: str) -> str:
        value = model.strip()
        if not value:
            return self.agent_model
        if value not in AGENT_MODEL_CHOICES:
            value = self.defaults.agent_model
        if value != self.agent_model:
            self.agent_model = value
            self.touch_revision()
        return self.agent_model

    # -------------------------------------------------------------------------
    def set_llm_provider(self, provider: str) -> str:
        value = provider.strip().lower()
        if not value:
            return self.llm_provider
        if value not in CLOUD_MODEL_CHOICES:
            value = self.defaults.llm_provider
        if value != self.llm_provider:
            self.llm_provider = value
            models = CLOUD_MODEL_CHOICES.get(value, [])
            if self.cloud_model not in models:
                self.cloud_model = models[0] if models else ""
            self.touch_revision()
        return self.llm_provider

    # -------------------------------------------------------------------------
    def set_cloud_model(self, model: str) -> str:
        value = model.strip()
        if not value:
            if self.cloud_model:
                self.cloud_model = ""
                self.touch_revision()
            return self.cloud_model
        models = CLOUD_MODEL_CHOICES.get(self.llm_provider, [])
        if value not in models:
            value = models[0] if models else ""
        if value != self.cloud_model:
            self.cloud_model = value
            self.touch_revision()
        return self.cloud_model

    # -------------------------------------------------------------------------
    def get_cloud_model(self) -> str:
        return self.cloud_model

    # -------------------------------------------------------------------------
    def set_ollama_temperature(self, t: float | None) -> float:
        if t is None:
            t = self.defaults.ollama_temperature
        rounded = round(float(t), 2)
        if rounded != self.ollama_temperature:
            self.ollama_temperature = rounded
            self.touch_revision()
        return self.ollama_temperature

    # -------------------------------------------------------------------------
    def set_ollama_reasoning(self, enabled: bool) -> bool:
        normalized = bool(enabled)
        if normalized != self.ollama_reasoning:
            self.ollama_reasoning = normalized
            self.touch_revision()
        return self.ollama_reasoning