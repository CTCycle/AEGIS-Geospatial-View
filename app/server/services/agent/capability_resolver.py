from __future__ import annotations

from typing import Any

from server.domain.extraction.models import TurnParseResult
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.runtime_registry import RuntimeRegistry

###############################################################################
class CapabilityResolver:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        capability_registry: CapabilityRegistry | None = None,
        runtime_registry: RuntimeRegistry | None = None,
    ) -> None:
        self.capability_registry = capability_registry or CapabilityRegistry()
        self.runtime_registry = runtime_registry or RuntimeRegistry()

    # -------------------------------------------------------------------------
    def resolve(self, turn: TurnParseResult) -> TurnParseResult:
        requested = [item.strip() for item in turn.requested_layers if item.strip()]
        if not requested:
            return turn

        if self._requests_unsupported_precipitation_mean(turn, requested):
            return turn.model_copy(
                update={
                    "requested_layers": [],
                    "capability_limitations": self._dedupe(
                        [
                            *turn.capability_limitations,
                            (
                                "Historical monthly-mean precipitation is not available "
                                "from the current executable catalog."
                            ),
                        ]
                    ),
                    "clarification_plan": {
                        "question": (
                            "I cannot calculate an October mean from the current layers. "
                            "Would you like current precipitation radar, current "
                            "precipitation rate, or a near-term forecast instead?"
                        ),
                        "reason": (
                            "The catalog contains current and forecast precipitation "
                            "capabilities, but no historical monthly aggregation source."
                        ),
                        "blocking_fields": [
                            "supported_precipitation_time_basis",
                        ],
                        "options": [
                            {
                                "option_id": "current_radar",
                                "label": "Current precipitation radar",
                            },
                            {
                                "option_id": "current_rate",
                                "label": "Current precipitation rate",
                            },
                            {
                                "option_id": "forecast",
                                "label": "Near-term precipitation forecast",
                            },
                        ],
                        "preserve_valid_results": True,
                        "apply_visualization_changes": False,
                    },
                    "ambiguities": self._dedupe(
                        [*turn.ambiguities, "unsupported_historical_precipitation_mean"]
                    ),
                    "expected_frontend_update": "clarification",
                }
            )

        resolved: list[str] = []
        unresolved: list[str] = []
        for layer in requested:
            capability_id = self._resolve_one(layer, turn)
            if capability_id is None:
                unresolved.append(layer)
            elif capability_id not in resolved:
                resolved.append(capability_id)

        if not unresolved:
            return turn.model_copy(update={"requested_layers": resolved})

        readable = ", ".join(unresolved)
        return turn.model_copy(
            update={
                "requested_layers": resolved,
                "capability_limitations": self._dedupe(
                    [
                        *turn.capability_limitations,
                        f"No enabled executable layer matched: {readable}.",
                    ]
                ),
                "clarification_plan": {
                    "question": (
                        f"I could not match **{readable}** to an enabled map layer. "
                        "Can you describe the data you want to see in different terms?"
                    ),
                    "reason": "No compatible executable catalog capability was found.",
                    "blocking_fields": ["geospatial_layer"],
                    "options": [],
                    "preserve_valid_results": True,
                    "apply_visualization_changes": False,
                },
                "ambiguities": self._dedupe(
                    [*turn.ambiguities, "unresolved_geospatial_capability"]
                ),
                "expected_frontend_update": "clarification",
            }
        )

    # -------------------------------------------------------------------------
    def _resolve_one(self, layer: str, turn: TurnParseResult) -> str | None:
        exact = self.capability_registry.get_capability(layer)
        if exact is not None:
            return layer if self.runtime_registry.is_enabled(layer) else None
        if "_" in layer:
            return None
        normalized = layer.casefold()
        text = f"{turn.user_text} {layer}".casefold()
        if self._is_precipitation_concept(normalized, text):
            if turn.temporal_signal.mode == "forecast" or "forecast" in text:
                return self._enabled("openmeteo_weather_forecast")
            if "radar" in text or "storm" in text:
                return self._enabled("rainviewer_precipitation_radar")
            if any(marker in text for marker in ("rate", "level", "intensity")):
                return self._enabled("IMERG_Precipitation_Rate")
            return self._enabled("rainviewer_precipitation_radar") or self._enabled(
                "IMERG_Precipitation_Rate"
            )

        ranked = sorted(
            (
                (self._score(layer, turn, item), str(item.get("id") or ""))
                for item in self._all_capabilities()
                if self.runtime_registry.is_enabled(str(item.get("id") or ""))
            ),
            reverse=True,
        )
        if not ranked or ranked[0][0] < 3:
            return None
        return ranked[0][1]

    # -------------------------------------------------------------------------
    def _score(
        self,
        layer: str,
        turn: TurnParseResult,
        capability: dict[str, Any],
    ) -> int:
        terms = set(self._tokens(layer))
        searchable = " ".join(
            str(value)
            for value in [
                capability.get("id"),
                capability.get("name"),
                capability.get("description"),
                *(capability.get("capabilities") or []),
                *((capability.get("metadata") or {}).get("keywords") or []),
                *((capability.get("metadata") or {}).get("action_tags") or []),
                *((capability.get("metadata") or {}).get("task_tags") or []),
                *((capability.get("agenticUse") or {}).get("plannerHints") or []),
            ]
        ).casefold()
        score = sum(2 for term in terms if len(term) > 2 and term in searchable)
        if turn.temporal_signal.mode == "forecast" and "forecast" in searchable:
            score += 4
        if turn.temporal_signal.mode == "current" and any(
            marker in searchable for marker in ("current", "radar", "dynamic")
        ):
            score += 2
        return score

    # -------------------------------------------------------------------------
    def _all_capabilities(self) -> list[dict[str, Any]]:
        return [
            *self.capability_registry.list_basemaps(),
            *self.capability_registry.list_overlays(),
            *self.capability_registry.list_cameras(),
            *self.capability_registry.list_transit(),
            *self.capability_registry.list_tools(),
        ]

    # -------------------------------------------------------------------------
    def _enabled(self, capability_id: str) -> str | None:
        if (
            self.capability_registry.get_capability(capability_id) is not None
            and self.runtime_registry.is_enabled(capability_id)
        ):
            return capability_id
        return None

    # -------------------------------------------------------------------------
    @classmethod
    def _requests_unsupported_precipitation_mean(
        cls,
        turn: TurnParseResult,
        requested: list[str],
    ) -> bool:
        text = f"{turn.user_text} {' '.join(requested)}".casefold()
        if not cls._is_precipitation_concept(" ".join(requested).casefold(), text):
            return False
        historical = turn.temporal_signal.mode == "historical" or any(
            month in text
            for month in (
                "january", "february", "march", "april", "may", "june",
                "july", "august", "september", "october", "november", "december",
            )
        )
        aggregate = any(
            marker in text for marker in ("mean", "average", "monthly", "climatology")
        )
        return historical and aggregate

    # -------------------------------------------------------------------------
    @staticmethod
    def _is_precipitation_concept(layer: str, text: str) -> bool:
        return any(
            marker in f"{layer} {text}"
            for marker in ("precipitation", "rain", "rainfall")
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _tokens(value: str) -> list[str]:
        normalized = "".join(
            character if character.isalnum() else " " for character in value.casefold()
        )
        return [item for item in normalized.split() if item]

    # -------------------------------------------------------------------------
    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        return list(dict.fromkeys(value for value in values if value))
