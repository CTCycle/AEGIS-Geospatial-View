from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class MapTypeResolution:
    map_type: str
    source: str


class MapTypeResolver:
    _lexicon: dict[str, str] = {
        "streets": "street",
        "addresses": "street",
        "roads": "street",
        "navigation": "street",
        "photographic": "satellite",
        "realistic": "satellite",
        "imagery": "satellite",
        "aerial": "satellite",
        "satellite": "satellite",
        "elevation": "terrain",
        "relief": "terrain",
        "topographic": "terrain",
        "minimal": "light",
        "clean": "light",
        "light": "light",
        "dark": "dark",
        "night mode": "dark",
    }

    def resolve(self, *, intent: dict[str, Any], user_text: str) -> MapTypeResolution:
        prefs = intent.get("map_preferences") if isinstance(intent.get("map_preferences"), dict) else {}
        model_type = str(prefs.get("map_type") or "auto")
        model_conf = float(prefs.get("map_type_confidence") or 0.0)
        lexical = self._infer_from_text(user_text)
        if lexical and (model_type == "auto" or model_conf < 0.45 or lexical != model_type):
            return MapTypeResolution(lexical, "heuristic")
        if model_type and model_type != "auto":
            return MapTypeResolution(model_type, "model")
        return MapTypeResolution("auto", "default")

    def _infer_from_text(self, text: str) -> str | None:
        lowered = text.lower()
        for phrase, map_type in self._lexicon.items():
            if phrase in lowered:
                return map_type
        return None
