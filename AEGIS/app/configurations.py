from __future__ import annotations

import json
import os
from typing import Any

from AEGIS.app.constants import RSC_PATH


###############################################################################
class Configuration:
    def __init__(self) -> None:
        self.config_path = os.path.join(RSC_PATH, "configuration.json")
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
        defaults: dict[str, Any] = {"model": "gpt-3.5-turbo"}
        if not os.path.exists(self.config_path):
            return defaults
        with open(self.config_path, "r", encoding="utf-8") as stream:
            try:
                loaded = json.load(stream)
            except json.JSONDecodeError:
                return defaults
        if not isinstance(loaded, dict):
            return defaults
        if "model" not in loaded:
            loaded["model"] = defaults["model"]
        return loaded


