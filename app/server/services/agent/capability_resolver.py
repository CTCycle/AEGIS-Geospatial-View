from __future__ import annotations

import unicodedata
from typing import Any, cast

from server.common.typing import is_json_array, json_array, json_object

from server.contracts.extraction import TurnParseResult
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.runtime_registry import RuntimeRegistry


_NON_DATA_CONCEPT_TAGS = frozenset(
    {
        # Presentation and interaction actions are not dataset identities.
        "show",
        "display",
        "view",
        "visualize",
        "visualise",
        "render",
        "plot",
        "find",
        "get",
        "list",
        "retrieve",
        "lookup",
        "look_up",
        "tell",
        "explain",
        "describe",
        "compare",
        "contrast",
        "add",
        "remove",
        "hide",
        "clear",
        "update",
        "switch",
        "change",
        "replace",
        "keep",
        "preserve",
        # Map/session and relative-location references are resolved elsewhere.
        "map",
        "location",
        "coordinates",
        "basemap",
        "overlay",
        "chat",
        "direct_query",
        "map_search",
        "place",
        "visualization",
        "visualisation",
        "catalog",
        "data",
        "query",
        "search",
        "direct",
        "tool",
        "near",
        "nearby",
        "around",
        "within",
        "here",
        "there",
        "this",
        "that",
        "current",
        "recent",
        "historical",
        # Structured map-interaction labels are not dataset identities.  The
        # model may emit these as action tags for a location-only request; the
        # map pipeline resolves the location and chooses the catalog-backed
        # basemap independently.
        "show_map",
        "map_center",
        "map_focus",
        "map_render",
        "map_display",
        "map_navigation",
        "navigate",
        "focus",
        "center",
        "zoom",
        "locate",
        "city",
        "country",
    }
)


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
        capabilities = self._all_capabilities()
        atomic_layer_refs = {
            self._normalize_text(str(item))
            for task in turn.atomic_tasks
            if isinstance(task, dict)
            for item in json_array(task.get("required_layers"))
            if str(item).strip()
        }
        grounded_layers = [
            str(item).strip()
            for item in turn.requested_layers
            if str(item).strip()
            and self._retain_requested_layer(
                str(item),
                turn=turn,
                capabilities=capabilities,
                atomic_layer_refs=atomic_layer_refs,
            )
        ]
        # A model can hallucinate an enabled catalog ID while extracting a
        # location-only request.  Determine focus from the internally
        # consistent, text-grounded layer set rather than allowing that ID to
        # turn a map navigation request into data retrieval.
        focus_turn = turn.model_copy(update={"requested_layers": grounded_layers})
        location_focus_only = self.is_location_focus_only(focus_turn, capabilities)
        requested = grounded_layers
        if location_focus_only:
            requested = [
                item
                for item in requested
                if self._is_location_focus_capability(item, capabilities, turn)
            ]
        requested_concepts = [
            str(item).strip()
            for item in turn.requested_concepts
            if str(item).strip()
        ]
        if not location_focus_only:
            requested.extend(requested_concepts)
        # Older model outputs placed semantic dataset concepts in action_tags.
        # Keep that typed field useful while excluding presentation-only words;
        # executable identity is still resolved exclusively against the catalog.
        if (
            not location_focus_only
            and not turn.requested_layers
            and not turn.requested_concepts
        ):
            requested.extend(
                item
                for item in turn.normalized_action.action_tags
                if self._is_data_concept(item)
            )
        for task in turn.atomic_tasks:
            required_layers = task.get("required_layers")
            if not isinstance(required_layers, list):
                continue
            requested.extend(
                str(item).strip()
                for item in cast(list[Any], required_layers)
                if str(item).strip()
                and self._retain_requested_layer(
                    str(item),
                    turn=turn,
                    capabilities=capabilities,
                    atomic_layer_refs=atomic_layer_refs,
                )
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
        poi_capability = self._resolve_one("poi", turn) if turn.poi_categories else None
        for layer in requested:
            capability_id = self._resolve_one(layer, turn)
            if capability_id is None:
                if poi_capability and self._is_poi_refinement(layer, turn):
                    if poi_capability not in resolved:
                        resolved.append(poi_capability)
                    continue
                unresolved.append(layer)
            elif capability_id not in resolved:
                resolved.append(capability_id)

        # POI categories are query refinements, not separate catalog entries.
        # Resolve the generic executable capability once and pass the category
        # through the typed argument contract for provider-side validation.
        if poi_capability and not resolved and not unresolved:
            resolved.append(poi_capability)

        if not unresolved:
            return turn.model_copy(
                update={
                    "requested_layers": resolved,
                    "requested_concepts": self._dedupe(turn.requested_concepts),
                    "overlay_commands": overlay_commands,
                }
            )

        readable = ", ".join(self._dedupe(unresolved))
        direct_query = turn.task_class == "direct_query"
        limitation = (
            f"No enabled executable data source matched: {readable}."
            if direct_query
            else f"No enabled executable layer matched: {readable}."
        )
        question = (
            f"The enabled catalog does not provide executable values for {readable}. "
            "Those values are unsupported by the current data sources."
            if direct_query
            else (
                f"I could not match {readable} to an enabled map layer. "
                "Can you describe the data you want to see in different terms?"
            )
        )
        blocking_field = "direct_data_source" if direct_query else "geospatial_layer"
        reason = (
            "No compatible executable direct data capability was found for the "
            "structured value request."
            if direct_query
            else (
                "No compatible executable catalog capability was found for "
                "the structured layer request."
            )
        )
        return turn.model_copy(
            update={
                "requested_layers": resolved,
                "requested_concepts": self._dedupe(turn.requested_concepts),
                "overlay_commands": overlay_commands,
                "capability_limitations": self._dedupe(
                    [
                        *turn.capability_limitations,
                        limitation,
                    ]
                ),
                "clarification_plan": {
                    "question": question,
                    "reason": reason,
                    "blocking_fields": [blocking_field],
                    "options": [],
                    "preserve_valid_results": True,
                    "apply_visualization_changes": bool(
                        overlay_commands or turn.requested_basemap
                    ),
                },
                "ambiguities": self._dedupe(
                    [*turn.ambiguities, "unresolved_geospatial_capability"]
                ),
                "expected_frontend_update": "clarification",
                "failure_category": "model_capability",
            }
        )

    # -------------------------------------------------------------------------
    @classmethod
    def is_location_focus_only(
        cls,
        turn: TurnParseResult,
        capabilities: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Detect a typed geocode/map-render graph with no data retrieval.

        A model can emit catalog-looking layer names while describing only a
        place lookup (for example, an entity name that happens to match a
        catalog keyword).  Atomic task types and explicit capability fields
        are the authoritative distinction.  The caller may provide a
        text-grounded layer view so an unanchored model hallucination cannot
        change the execution mode.
        """

        if turn.task_class != "map_search":
            return False
        if turn.poi_categories or turn.required_data_sources:
            return False
        if turn.required_tool_category:
            return False
        if any(
            command.action in {"add", "show", "update"}
            for command in turn.overlay_commands
        ):
            return False
        if turn.normalized_action.action_id in {
            "data_layer_query",
            "dataset_display",
            "overlay_control",
            "visible_layer_interrogation",
            "map_external_source_combination",
        }:
            return False
        if turn.requested_layers:
            if capabilities is None:
                # After capability resolution, any remaining layer is an
                # enabled catalog identity and therefore an actual data
                # request.  Before resolution, unknown model labels are
                # allowed to be discarded by the catalog-aware caller below.
                return False
            for requested_layer in turn.requested_layers:
                normalized = cls._normalize_text(str(requested_layer))
                capability = next(
                    (
                        item
                        for item in capabilities
                        if cls._normalize_text(str(item.get("id") or ""))
                        == normalized
                    ),
                    None,
                )
                if capability is None:
                    # An unknown layer is not evidence of a location-only
                    # request.  Leave it in the normal resolution path so a
                    # genuinely requested unavailable layer receives an
                    # explicit capability clarification.
                    return False
                kind = str(
                    capability.get("capabilityKind")
                    or capability.get("capability_kind")
                    or ""
                ).strip().casefold()
                if kind != "basemap":
                    return False
        if not turn.atomic_tasks:
            return bool(turn.location_signals or turn.map_target or turn.entity_target)
        for task in turn.atomic_tasks:
            if not isinstance(task, dict):
                continue
            required_layers = task.get("required_layers")
            if isinstance(required_layers, list) and any(
                str(item).strip() for item in required_layers
            ):
                return False
            task_type = str(task.get("task_type") or "").strip().casefold()
            if task_type and not any(
                marker in task_type
                for marker in ("geocode", "location", "map", "viewport", "focus")
            ):
                return False
        return bool(turn.location_signals or turn.map_target or turn.entity_target)

    # -------------------------------------------------------------------------
    def _is_location_focus_capability(
        self,
        value: str,
        capabilities: list[dict[str, Any]],
        turn: TurnParseResult,
    ) -> bool:
        normalized = self._normalize_text(value)
        if not normalized:
            return False
        for capability in capabilities:
            capability_id = str(capability.get("id") or "").strip()
            if self._normalize_text(capability_id) != normalized:
                continue
            kind = str(
                capability.get("capabilityKind")
                or capability.get("capability_kind")
                or ""
            ).strip().casefold()
            if kind == "basemap":
                return self._is_usable(capability, turn)
        return False

    # -------------------------------------------------------------------------
    def _retain_requested_layer(
        self,
        value: str,
        *,
        turn: TurnParseResult,
        capabilities: list[dict[str, Any]],
        atomic_layer_refs: set[str],
    ) -> bool:
        """Keep a model layer only when it has typed or textual support."""

        normalized = self._normalize_text(value)
        if not normalized:
            return False
        if normalized in atomic_layer_refs:
            return True
        user_text = self._normalize_text(turn.user_text)
        if normalized in user_text:
            return True
        if any(
            str(task.get("task_type") or "").strip().casefold()
            and not any(
                marker in str(task.get("task_type") or "").strip().casefold()
                for marker in ("geocode", "location", "map", "viewport", "focus")
            )
            for task in turn.atomic_tasks
            if isinstance(task, dict)
        ):
            return True
        if (
            turn.normalized_action.action_id
            in {
                "data_layer_query",
                "dataset_display",
                "overlay_control",
                "visible_layer_interrogation",
                "map_external_source_combination",
            }
            or turn.temporal_signal.mode != "none"
            or turn.temporal_signal.aggregation != "none"
        ):
            # A typed data/temporal request should be allowed to reach the
            # normal capability validator.  If the requested layer is
            # unavailable or incompatible, it will produce a categorized
            # clarification rather than being silently discarded.
            return True

        capability = next(
            (
                item
                for item in capabilities
                if self._normalize_text(str(item.get("id") or "")) == normalized
            ),
            None,
        )
        if capability is None:
            # Keep unknown values so the normal resolver can report a typed
            # model-capability clarification instead of silently dropping a
            # user-requested but unavailable layer.
            return True

        metadata = json_object(capability.get("metadata"))
        evidence_values = [
            str(capability.get("name") or ""),
            *[str(item) for item in json_array(capability.get("capabilities"))],
            *[str(item) for item in json_array(metadata.get("keywords"))],
            *[str(item) for item in json_array(metadata.get("action_tags"))],
            *[str(item) for item in json_array(metadata.get("task_tags"))],
            *[
                str(item)
                for item in json_array(
                    json_object(capability.get("agenticUse")).get("plannerHints")
                )
            ],
        ]
        user_tokens = set(self._tokens(turn.user_text))
        generic_tokens = {
            "add",
            "data",
            "display",
            "layer",
            "map",
            "overlay",
            "show",
            "site",
            "the",
            "view",
        }
        for evidence in evidence_values:
            evidence_tokens = {
                token
                for token in self._tokens(evidence)
                if token not in generic_tokens
            }
            if evidence_tokens & user_tokens:
                return True
        return False

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

        candidates = [
            item
            for item in capabilities
            if self._is_usable(item, turn)
            and ("_" not in query or self._query_token_coverage(query, item) == 1.0)
        ]
        role_candidates = [
            item
            for item in candidates
            if self._matches_task_role(item, turn.task_class)
        ]
        # A semantic concept can be published both as a renderable dataset and
        # as a direct text tool. Prefer the catalog role required by the task,
        # while retaining a fallback when a catalog only exposes the other
        # role. Exact capability IDs above remain authoritative.
        if role_candidates:
            candidates = role_candidates

        ranked = sorted(
            (
                (self._score(query, item), str(item.get("id") or ""))
                for item in candidates
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
    @staticmethod
    def _matches_task_role(capability: dict[str, Any], task_class: str) -> bool:
        capability_type = str(capability.get("type") or "").strip().casefold()
        if task_class == "direct_query":
            return capability_type == "direct-tool"
        if task_class == "map_search":
            return capability_type != "direct-tool"
        return True

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
        if callable(supports_mode):
            required_mode = {
                "map_search": "map",
                "direct_query": "direct_text",
            }.get(turn.task_class)
            if required_mode is not None and not supports_mode(
                capability_id, required_mode
            ):
                return False
        return self._supports_temporal_request(capability, turn)

    # -------------------------------------------------------------------------
    @staticmethod
    def _is_data_concept(value: object) -> bool:
        normalized = str(value or "").strip().casefold().replace("-", "_")
        return normalized not in _NON_DATA_CONCEPT_TAGS

    # -------------------------------------------------------------------------
    @classmethod
    def _is_poi_refinement(cls, value: object, turn: TurnParseResult) -> bool:
        normalized = cls._normalize_text(str(value or ""))
        if not normalized:
            return False
        return any(
            normalized == cls._normalize_text(str(category))
            for category in turn.poi_categories
        )

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
        if not is_json_array(declared_modes):
            declared_modes = capability.get("supported_temporal_modes")
        if is_json_array(declared_modes) and declared_modes:
            allowed_modes = {
                str(item).strip().casefold()
                for item in declared_modes
                if str(item).strip()
            }
            if temporal.mode not in allowed_modes and temporal.mode != "none":
                return False

        declared_aggregations = metadata.get("supported_aggregations")
        if not is_json_array(declared_aggregations):
            declared_aggregations = capability.get("supported_aggregations")
        if is_json_array(declared_aggregations) and declared_aggregations:
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
