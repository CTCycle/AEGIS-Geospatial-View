from __future__ import annotations

import json
from typing import Any
from os import path

from AEGIS.app.constants import SETUP_DIR
CONFIGURATION_CACHE: dict[str, Any] | None = None
CONFIGURATION_FILE = path.join(SETUP_DIR, "configurations.json")


###############################################################################
class Configuration:
    def __init__(self) -> None:
        self.configuration = self.load_configuration()

    # -------------------------------------------------------------------------
    def load_configuration(self) -> dict[str, Any]:
        global CONFIGURATION_CACHE
        if CONFIGURATION_CACHE is not None:
            return CONFIGURATION_CACHE
        with open(CONFIGURATION_FILE, encoding="utf-8") as file:
            configuration = json.load(file)
        if not isinstance(configuration, dict):
            raise ValueError("Configuration file must contain a JSON object.")
        CONFIGURATION_CACHE = configuration
        return configuration

    # -------------------------------------------------------------------------
    def get_configuration(self) -> dict[str, Any]:
        return self.configuration

    # -------------------------------------------------------------------------
    def get_value(self, key: str, default: Any | None = None) -> Any:
        return self.configuration.get(key, default)
