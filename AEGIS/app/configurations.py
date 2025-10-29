from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from AEGIS.app.constants import (
    CONFIGURATION_PATH,
    DEFAULT_AGENTIC_TEMPERATURE,
    FILTER_CHOICES,
    MAX_AGENTIC_TEMPERATURE,
    MIN_AGENTIC_TEMPERATURE,
    OPENAI_MODEL_CHOICES,
    AGENT_MODEL_CHOICES,
)


###############################################################################
def normalize_string_list(value: Any, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return list(fallback)
    normalized: list[str] = []
    for entry in value:
        if not isinstance(entry, str):
            continue
        stripped = entry.strip()
        if stripped and stripped not in normalized:
            normalized.append(stripped)
    return normalized or list(fallback)


###############################################################################
class Configuration:
    def __init__(self) -> None:
        self.config_path = CONFIGURATION_PATH
        self.configuration = self.load_configuration()

    # -------------------------------------------------------------------------
    def get_configuration(self) -> dict[str, Any]:
        return self.configuration

    # -------------------------------------------------------------------------
    def get_section(self, name: str) -> dict[str, Any]:
        value = self.configuration.get(name)
        if isinstance(value, dict):
            return value
        return {}

    # -------------------------------------------------------------------------
    def load_configuration(self) -> dict[str, Any]:
        if not os.path.exists(self.config_path):
            return {}
        with open(self.config_path, "r", encoding="utf-8") as stream:
            try:
                loaded = json.load(stream)
            except json.JSONDecodeError:
                return {}
        if isinstance(loaded, dict):
            return loaded
        return {}


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

    def __init__(self, base_configuration: Configuration | None = None) -> None:
        configuration = base_configuration or Configuration()
        geographics_section = configuration.get_section("geographics")
        filter_choices = normalize_string_list(
            geographics_section.get("filter_choices"), FILTER_CHOICES
        )
        openai_choices = normalize_string_list(
            geographics_section.get("openai_model_choices"), OPENAI_MODEL_CHOICES
        )
        agent_choices = normalize_string_list(
            geographics_section.get("agent_model_choices"), AGENT_MODEL_CHOICES
        )

        default_filter = geographics_section.get("default_filter")
        if isinstance(default_filter, str):
            candidate = default_filter.strip()
            self.default_filter = candidate if candidate in filter_choices else filter_choices[0]
        else:
            self.default_filter = filter_choices[0]

        default_agent_model = geographics_section.get("default_agent_model")
        if isinstance(default_agent_model, str):
            candidate = default_agent_model.strip()
            self.default_agent_model = (
                candidate if candidate in agent_choices else agent_choices[0]
            )
        else:
            self.default_agent_model = agent_choices[0]

        default_use_cloud = geographics_section.get("default_use_cloud")
        self.default_use_cloud = bool(default_use_cloud) if isinstance(default_use_cloud, bool) else False

        temperature_min = geographics_section.get("min_agentic_temperature")
        temperature_max = geographics_section.get("max_agentic_temperature")
        self.agentic_temperature_min = (
            float(temperature_min)
            if isinstance(temperature_min, (int, float))
            else float(MIN_AGENTIC_TEMPERATURE)
        )
        self.agentic_temperature_max = (
            float(temperature_max)
            if isinstance(temperature_max, (int, float))
            else float(MAX_AGENTIC_TEMPERATURE)
        )
        if self.agentic_temperature_min >= self.agentic_temperature_max:
            self.agentic_temperature_min = float(MIN_AGENTIC_TEMPERATURE)
            self.agentic_temperature_max = float(MAX_AGENTIC_TEMPERATURE)

        temperature_default = geographics_section.get("default_agentic_temperature")
        if isinstance(temperature_default, (int, float)):
            candidate = float(temperature_default)
        else:
            candidate = float(DEFAULT_AGENTIC_TEMPERATURE)
        if candidate < self.agentic_temperature_min:
            candidate = self.agentic_temperature_min
        if candidate > self.agentic_temperature_max:
            candidate = self.agentic_temperature_max
        self.agentic_temperature_default = candidate

        self.filter_choices = filter_choices
        self.openai_model_choices = openai_choices
        self.agent_model_choices = agent_choices

