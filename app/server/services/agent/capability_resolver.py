from __future__ import annotations

import unicodedata
from typing import Any, cast

from server.common.typing import json_array, json_object

from server.contracts.extraction import TurnParseResult
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.runtime_registry import RuntimeRegistry


###############################################################################
class CapabilityResolver:
    """Resolve parser concepts against the executable catalog.

    The parser owns language interpretation and this service owns capability
    identity. No provider, city, or example phrase is selected here by
    inspecting the raw user message.
    """

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        capability_registry: CapabilityRegistry,
        runtime_registry: RuntimeRegistry,
    ) -> None:
        self.capability_registry = capability_registry
        self.runtime_registry = runtime_registry

    # -------------------------------------------------------------------------
    def resolve(self, turn: TurnParseResult) -> TurnParseResult:
        requested = [
            str(item).strip() for item in turn.requested_layers if str(item).strip()
        ]
        for task in turn.atomic_tasks:
            required_layers = task.get("required_layers")
            if not isinstance(required_layers, list):
                continue
            requested.extend(
                str(item).strip()
                for item in cast(list[Any], required_layers)
                if str(item).strip()
            )

        overlay_commands = self._resolve_overlay_commands(
            turn.overlay_commands,
            turn,
        )
        for command in overlay_commands:
            if command.action not in {"add", "show", "update"}:
                continue
            requested.extend(command.selector.capability_ids)
            requested.extend(command.selector.concepts)
            requested.extend(command.selector.labels)
        requested = self._dedupe(requested)

        resolved: list[str] = []
        unresolved: list[str] = []
        for layer in requested:
            capability_id = self._resolve_one(layer, turn)
            if capability_id is None:
                unresolved.append(layer)
            elif capability_id not in resolved:
                resolved.append(capability_id)

        if not unresolved:
            return turn.model_copy(
                update={
                    "requested_layers": resolved,
                    "overlay_commands": overlay_commands,
                }
            )

        readable = ", ".join(self._dedupe(unresolved))
        return turn.model_copy(
            update={
                "requested_layers": resolved,
                "overlay_commands": overlay_commands,
                "capability_limitations": self._dedupe(
                    [
                        *turn.capability_limitations,
                        f"No enabled executable layer matched: {readable}.",
                    ]
                ),
                "clarification_plan": {
                    "question": (
                        f"I could not match {readable} to an enabled map layer. "
                        "Can you describe the data you want to see in different terms?"
                    ),
                    "reason": (
                        "No compatible executable catalog capability was found for "
                        "the structured layer request."
                    ),
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
    def _resolve_overlay_commands(
        self,
        commands: list[Any],
        turn: TurnParseResult,
    ) -> list[Any]:
        resolved_commands: list[Any] = []
        for command in commands:
            selector = command.selector
            capability_ids: list[str] = []
            for value in selector.capability_ids:
                capability_id = self._resolve_one(value, turn)
                normalized = capability_id or str(value).strip()
                if normalized and normalized not in capability_ids:
                    capability_ids.append(normalized)
            for value in [*selector.concepts, *selector.labels]:
                capability_id = self._resolve_one(value, turn)
                if capability_id is not None and capability_id not in capability_ids:
                    capability_ids.append(capability_id)
            if capability_ids != selector.capability_ids:
                command = command.model_copy(
                    update={
                        "selector": selector.model_copy(
                            update={"capability_ids": capability_ids}
                        )
                    }
                )
            resolved_commands.append(command)
        return resolved_commands

    # -------------------------------------------------------------------------
    def _resolve_one(self, layer: str, turn: TurnParseResult) -> str | None:
        query = str(layer).strip()
        if not query:
            return None

        capabilities = self._all_capabilities()
        normalized_query = self._normalize_text(query)
        exact = next(
            (
                item
                for item in capabilities
                if self._normalize_text(str(item.get("id") or "")) == normalized_query
            ),
            None,
        )
        if exact is not None:
            capability_id = str(exact.get("id") or "").strip()
            return capability_id if self._is_usable(exact, turn) else None

        ranked = sorted(
            (
                (self._score(query, item), str(item.get("id") or ""))
                for item in capabilities
                if self._is_usable(item, turn)
                and ("_" not in query or self._query_token_coverage(query, item) == 1.0)
            ),
            key=lambda value: (-value[0], value[1]),
        )
        ranked = [item for item in ranked if item[0] > 0 and item[1]]
        if not ranked:
            return None

        top_score = ranked[0][0]
        top_ids = [item[1] for item in ranked if item[0] == top_score]
        # A semantic request with two equally suitable executable targets is
        # ambiguous. Ask the parser/UI to clarify instead of choosing a
        # provider by list order.
        if len(top_ids) != 1:
            return None
        return top_ids[0]

    # -------------------------------------------------------------------------
    def _is_usable(
        self,
        capability: dict[str, Any],
        turn: TurnParseResult,
    ) -> bool:
        capability_id = str(capability.get("id") or "").strip()
        if not capability_id or not self.runtime_registry.is_enabled(capability_id):
            return False
        supports_mode = getattr(self.runtime_registry, "supports_mode", None)
        if callable(supports_mode) and turn.task_class == "map_search":
            if not supports_mode(capability_id, "map"):
                return False
        return self._supports_temporal_request(capability, turn)

    # -------------------------------------------------------------------------
    @staticmethod
    def _supports_temporal_request(
        capability: dict[str, Any],
        turn: TurnParseResult,
    ) -> bool:
        temporal = turn.temporal_signal
        if temporal.mode == "none" and temporal.aggregation == "none":
            return True

        metadata = json_object(capability.get("metadata"))
        declared_modes = metadata.get("supported_temporal_modes")
        if not isinstance(declared_modes, list):
            declared_modes = capability.get("supported_temporal_modes")
        if isinstance(declared_modes, list) and declared_modes:
            allowed_modes = {
                str(item).strip().casefold()
                for item in declared_modes
                if str(item).strip()
            }
            if temporal.mode not in allowed_modes and temporal.mode != "none":
                return False

        declared_aggregations = metadata.get("supported_aggregations")
        if not isinstance(declared_aggregations, list):
            declared_aggregations = capability.get("supported_aggregations")
        if isinstance(declared_aggregations, list) and declared_aggregations:
            allowed_aggregations = {
                str(item).strip().casefold()
                for item in declared_aggregations
                if str(item).strip()
            }
            if temporal.aggregation not in allowed_aggregations:
                return False

        # A manifest that explicitly describes a dynamic/current source cannot
        # satisfy a historical request unless it also declares historical
        # support. Unknown metadata remains permissive so catalog evolution
        # does not silently make capabilities unusable.
        behavior = str(metadata.get("temporal_behavior") or "").casefold()
        if temporal.mode == "historical" and behavior:
            historical_markers = ("historical", "archive")
            if not any(marker in behavior for marker in historical_markers):
                return False
        return True

    # -------------------------------------------------------------------------
    def _score(
        self,
        query: str,
        capability: dict[str, Any],
    ) -> int:
        normalized_query = self._normalize_text(query)
        query_tokens = set(self._tokens(query))
        if not query_tokens:
            return 0

        metadata = json_object(capability.get("metadata"))
        fields: tuple[tuple[int, list[str]], ...] = (
            (8, [str(capability.get("id") or "")]),
            (6, [str(capability.get("name") or ""), str(metadata.get("label") or "")]),
            (5, [str(item) for item in json_array(capability.get("capabilities"))]),
            (5, [str(item) for item in json_array(metadata.get("keywords"))]),
            (4, [str(item) for item in json_array(metadata.get("action_tags"))]),
            (3, [str(item) for item in json_array(metadata.get("task_tags"))]),
            (
                4,
                [
                    str(item)
                    for item in json_array(
                        json_object(capability.get("agenticUse")).get("plannerHints")
                    )
                ],
            ),
            (2, [str(item) for item in json_array(metadata.get("primary_use_cases"))]),
        )
        score = 0
        for weight, values in fields:
            for value in values:
                normalized_value = self._normalize_text(value)
                if not normalized_value:
                    continue
                value_tokens = set(self._tokens(value))
                overlap = len(query_tokens & value_tokens)
                if overlap:
                    score += weight * overlap
                if normalized_query == normalized_value:
                    score += weight * 3
                elif len(query_tokens) > 1 and normalized_query in normalized_value:
                    score += weight
        return score

    # -------------------------------------------------------------------------
    def _query_token_coverage(
        self,
        query: str,
        capability: dict[str, Any],
    ) -> float:
        query_tokens = set(self._tokens(query))
        if not query_tokens:
            return 0.0
        metadata = json_object(capability.get("metadata"))
        searchable_values = [
            str(capability.get("id") or ""),
            str(capability.get("name") or ""),
            *[str(item) for item in json_array(capability.get("capabilities"))],
            *[str(item) for item in json_array(metadata.get("keywords"))],
        ]
        searchable_tokens = set(self._tokens(" ".join(searchable_values)))
        return len(query_tokens & searchable_tokens) / len(query_tokens)

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
    @staticmethod
    def _normalize_text(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
        return " ".join(
            "".join(
                character if character.isalnum() else " " for character in normalized
            ).split()
        )

    # -------------------------------------------------------------------------
    @classmethod
    def _tokens(cls, value: str) -> list[str]:
        return cls._normalize_text(value).split()

    # -------------------------------------------------------------------------
    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        return list(
            dict.fromkeys(value.strip() for value in values if value and value.strip())
        )
