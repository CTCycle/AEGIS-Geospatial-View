from __future__ import annotations

import re
from typing import Any, cast

from server.common.typing import is_json_object, json_object
from server.contracts.extraction import (
    ContextQuery,
    ConversationContextSnapshot,
    LocationSignal,
    NormalizedAction,
    TemporalAggregation,
    TemporalGranularity,
    TemporalMode,
    TemporalSignal,
    TurnParseResult,
    ViewportIntent,
)
from server.domain.agent.actions import AgentAction
from server.services.geospatial.capability_registry import normalized_execution_contract

###############################################################################
class DeterministicIntentRecoveryService:
    """Recover explicit location/data requests when structured parsing fails.

    This is deliberately a narrow language boundary.  It does not attempt to
    replace the model parser: a request must contain an explicit coordinate or
    place phrase and either a clear map verb or a catalog-recognizable data
    concept.  Ambiguous, deictic, and unsupported requests continue through
    the normal parser failure diagnostic.
    """

    RECOVERY_WARNING = (
        "Structured agent extraction failed; the explicit location and "
        "catalog-backed data request was executed deterministically."
    )

    _RECOVERABLE_FAILURE_CODES = frozenset(
        {
            "provider_timeout",
            "application_deadline_exceeded",
            "structured_invalid_payload",
            "structured_contract_incomplete",
            "response_parsing_failed",
        }
    )

    _COORDINATE_PATTERN = re.compile(
        r"(?P<lat>[+-]?\d{1,2}(?:\.\d+)?)\s*[,;]\s*"
        r"(?P<lon>[+-]?\d{1,3}(?:\.\d+)?)"
    )
    _LOCATION_PATTERN = re.compile(
        r"\b(?:in|near|around|at|over|of|for)\s+"
        r"(?P<location>[^?.!;]+)",
        flags=re.IGNORECASE,
    )
    _LOCATION_TAIL_PATTERN = re.compile(
        r"\s+(?:with|showing|displaying|today|tomorrow|now|currently|please|"
        r"for\s+(?:today|tomorrow|now)|and\s+(?:the\s+)?(?:current\s+)?"
        r"(?:weather|forecast|air\s+quality|humidity|pressure|wind|"
        r"temperature|precipitation)|on\s+(?:the\s+)?map|"
        r"as\s+(?:a\s+)?map)\b",
        flags=re.IGNORECASE,
    )
    _MAP_LANGUAGE_PATTERN = re.compile(
        r"\b(?:map|on\s+(?:the\s+)?map|as\s+(?:a\s+)?map|"
        r"visuali[sz]e|plot|locate|find|center|centre|where\s+is)\b",
        flags=re.IGNORECASE,
    )
    _PROXIMITY_PATTERN = re.compile(
        r"\b(?:near|nearby|around|within)\b",
        flags=re.IGNORECASE,
    )
    _DISTANCE_DEPENDENT_PROXIMITY_PATTERN = re.compile(
        r"\b(?:near|nearby|within)\b",
        flags=re.IGNORECASE,
    )
    _DISTANCE_PATTERN = re.compile(
        r"\b(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>"
        r"km|kilometers?|kilometres?|m|meters?|metres?|mi|miles?)\b",
        flags=re.IGNORECASE,
    )
    _TEMPORAL_WINDOW_PATTERN = re.compile(
        r"\b(?:"
        r"(?:last|past|previous)\s+"
        r"(?:(?:\d{1,3})\s+)?"
        r"(?:minutes?|mins?|hours?|hrs?|days?|weeks?|months?|years?)"
        r"|(?:today|yesterday|tomorrow)"
        r"|(?:(?:this|current|last)\s+week)"
        r"|(?:from|since|between)\s+\d{4}-\d{2}-\d{2}"
        r"(?:\s+(?:to|and)\s+\d{4}-\d{2}-\d{2})?"
        r")\b",
        flags=re.IGNORECASE,
    )
    _CATALOG_STOPWORDS = frozenset(
        {
            "a",
            "an",
            "and",
            "as",
            "at",
            "by",
            "for",
            "from",
            "in",
            "is",
            "it",
            "me",
            "near",
            "nearby",
            "of",
            "on",
            "or",
            "over",
            "please",
            "show",
            "the",
            "this",
            "to",
            "today",
            "tomorrow",
            "around",
            "within",
            "current",
            "recent",
            "now",
            "map",
            "km",
            "kilometer",
            "kilometers",
            "kilometre",
            "kilometres",
            "meter",
            "meters",
            "metre",
            "metres",
            "mile",
            "miles",
        }
    )
    _ATTRIBUTE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
        (
            "humidity",
            re.compile(r"\b(?:relative\s+)?humid(?:ity|ities)\b", re.IGNORECASE),
        ),
        ("pressure", re.compile(r"\b(?:air\s+)?pressure\b", re.IGNORECASE)),
        ("wind", re.compile(r"\bwind(?:\s+(?:speed|direction|gusts?))?\b", re.IGNORECASE)),
        (
            "air quality",
            re.compile(r"\bair\s+quality\b|\b(?:air\s+)?pollution\b", re.IGNORECASE),
        ),
        ("pm2.5", re.compile(r"\bpm\s*2(?:\.\s*5)?\b", re.IGNORECASE)),
        ("temperature", re.compile(r"\btemperatures?\b", re.IGNORECASE)),
        (
            "precipitation",
            re.compile(r"\b(?:precipitation|rain(?:fall)?|snow)\b", re.IGNORECASE),
        ),
        ("weather", re.compile(r"\b(?:weather|forecast)\b", re.IGNORECASE)),
    )
    _INVALID_LOCATION_VALUES = frozenset(
        {
            "a map",
            "the map",
            "map",
            "data",
            "weather",
            "the weather",
            "forecast",
            "today",
            "tomorrow",
            "now",
            "here",
            "there",
            "me",
            "the area",
            "this area",
        }
    )

    # -------------------------------------------------------------------------
    @classmethod
    def recover_explicit_request(
        cls,
        *,
        user_message: str,
        memory_snapshot: dict[str, Any],
        conversation_messages: list[dict[str, Any]],
        provider_error: dict[str, Any] | None,
        capability_catalog: list[dict[str, Any]] | None = None,
        latest_contract: dict[str, Any] | None = None,
    ) -> TurnParseResult | None:
        """Return a safe executable contract for an explicit parser failure."""

        failure_code = str((provider_error or {}).get("code") or "").strip()
        failure_category = str(
            (provider_error or {}).get("category") or ""
        ).strip()
        if (
            failure_code not in cls._RECOVERABLE_FAILURE_CODES
            and failure_category != "response_parsing"
        ):
            return None

        prior_request = cls._pending_clarification_request(
            user_message=user_message,
            conversation_messages=conversation_messages,
            capability_catalog=capability_catalog,
            latest_contract=latest_contract,
        )
        analysis_message = (
            f"{prior_request} {user_message}" if prior_request else user_message
        )

        location = cls._extract_location_signal(analysis_message)
        if location is None:
            return None

        attributes = [
            label
            for label, pattern in cls._ATTRIBUTE_PATTERNS
            if pattern.search(analysis_message)
        ]
        catalog_concepts = cls._catalog_concepts(analysis_message, capability_catalog)
        concepts = cls._ordered_concepts(
            analysis_message,
            cls._dedupe([*attributes, *catalog_concepts]),
        )
        distance_m = cls._extract_distance_m(analysis_message)
        if cls._requires_catalog_distance(
            message=analysis_message,
            attributes=attributes,
            catalog_concepts=catalog_concepts,
            capability_catalog=capability_catalog,
            distance_m=distance_m,
        ):
            return None
        if not concepts and not cls._MAP_LANGUAGE_PATTERN.search(analysis_message):
            return None

        map_request = bool(cls._MAP_LANGUAGE_PATTERN.search(analysis_message))

        action_id = (
            AgentAction.DATA_LAYER_QUERY.value
            if concepts
            else AgentAction.LOCATION_RENDER.value
        )
        action_tags = ["deterministic_recovery", *attributes]
        task_tags = ["map" if map_request else "direct_query"]
        if concepts:
            task_tags.append("data")

        recovery_error = dict(provider_error or {})
        recovery_error.update(
            {
                "recovered": True,
                "recovery": (
                    "clarification_follow_up"
                    if prior_request
                    else "explicit_catalog_request"
                ),
            }
        )

        temporal_signal = cls._recovered_temporal_signal(
            user_message=user_message,
            analysis_message=analysis_message,
            latest_contract=latest_contract if prior_request else None,
        )

        recovered = TurnParseResult(
            user_text=user_message,
            conversation_context=ConversationContextSnapshot(
                recent_messages=cls._normalize_recent_messages(conversation_messages),
                memory_snapshot=dict(memory_snapshot),
            ),
            task_class="map_search" if map_request else "direct_query",
            location_signals=[location],
            normalized_action=NormalizedAction(
                action_id=action_id,
                action_label=(
                    "Catalog-backed map data request"
                    if concepts
                    else "Catalog-backed location map"
                ),
                task_tags=task_tags,
                action_tags=action_tags,
                requested_visualizations=["map"],
                requires_location=True,
            ),
            temporal_signal=temporal_signal,
            context_query=ContextQuery(kind="none"),
            parser_confidence=0.82,
            relationship="new_task",
            map_target=location.normalized_value or location.raw_value,
            requested_concepts=concepts,
            requested_attributes=attributes,
            radius_m=distance_m,
            presentation_mode="both" if map_request else "text",
            requested_basemap=cls._active_basemap(memory_snapshot) or "osm_default",
            tools_needed=True,
            direct_response_sufficient=False,
            expected_frontend_update="map_session" if map_request else "chat",
            viewport_intent=ViewportIntent(scope="auto"),
            provider_error=recovery_error,
            failure_category=None,
        )
        if prior_request and is_json_object(latest_contract):
            return cls._continue_pending_request(
                recovered=recovered,
                latest_contract=latest_contract,
            )
        return recovered

    # -------------------------------------------------------------------------
    @classmethod
    def continue_pending_request(
        cls,
        *,
        turn: TurnParseResult,
        user_message: str,
        latest_contract: dict[str, Any] | None,
        capability_catalog: list[dict[str, Any]] | None = None,
    ) -> TurnParseResult | None:
        """Complete a typed clarification without replacing its parent task.

        A clarification answer is a slot value, not a new task.  The model may
        therefore return a valid but incomplete interpretation of the answer
        (for example, a bare place name).  Only a contract that explicitly
        records a pending clarification can activate this continuation path;
        the normal parser and resolver remain authoritative for all other
        turns.
        """

        if not is_json_object(latest_contract):
            return None
        if not cls._contract_needs_clarification(latest_contract):
            return None
        provider_error = turn.provider_error
        if is_json_object(provider_error):
            code = str(provider_error.get("code") or "").strip()
            category = str(provider_error.get("category") or "").strip()
            if (
                code not in cls._RECOVERABLE_FAILURE_CODES
                and category != "response_parsing"
            ):
                return None

        pending_fields = cls._pending_field_kinds(latest_contract)
        if not pending_fields:
            return None
        updates: dict[str, Any] = {}
        answered_fields: set[str] = set()

        if "location" in pending_fields:
            location_signals = list(turn.location_signals)
            if not location_signals:
                location = cls._extract_bare_location_answer(
                    user_message, capability_catalog
                )
                if location is not None:
                    location_signals = [location]
            if location_signals:
                updates["location_signals"] = location_signals
                answered_fields.add("location")

        if "temporal" in pending_fields:
            temporal = cls._clarification_temporal_signal(
                turn,
                user_message,
                latest_contract=latest_contract,
            )
            if temporal is not None:
                updates["temporal_signal"] = temporal
                answered_fields.add("temporal")

        if "radius" in pending_fields:
            radius = turn.radius_m or cls._extract_distance_m(user_message)
            if radius is not None:
                updates["radius_m"] = radius
                answered_fields.add("radius")

        if "quantitative" in pending_fields:
            if turn.result_limit is not None:
                answered_fields.add("quantitative")
            else:
                filters = turn.filters if is_json_object(turn.filters) else {}
                if any(
                    filters.get(key) is not None
                    for key in ("top_n", "limit", "magnitude_threshold", "min_magnitude")
                ):
                    answered_fields.add("quantitative")

        if not pending_fields.issubset(answered_fields):
            return None

        if updates:
            turn = turn.model_copy(update=updates)
        if is_json_object(turn.provider_error):
            continuation_error = dict(turn.provider_error)
            continuation_error.update(
                {"recovered": True, "recovery": "clarification_follow_up"}
            )
            turn = turn.model_copy(update={"provider_error": continuation_error})
        return cls._continue_pending_request(
            recovered=turn,
            latest_contract=latest_contract,
        )

    # -------------------------------------------------------------------------
    @classmethod
    def _continue_pending_request(
        cls,
        *,
        recovered: TurnParseResult,
        latest_contract: dict[str, Any],
    ) -> TurnParseResult:
        """Carry the validated task contract across a clarification answer.

        A clarification answer supplies a missing constraint; it does not
        replace the operation that was waiting for that constraint.  Preserve
        the prior executable fields as a contract-level operation so every
        layer, provider, and data type follows the same normal resolver and
        native-tool path after recovery.
        """

        payload = recovered.model_dump(mode="python")
        inherited_fields = (
            "task_class",
            "normalized_action",
            "geographic_relationships",
            "operations",
            "filters",
            "presentation_requirements",
            "context_query",
            "requested_layers",
            "overlay_commands",
            "poi_categories",
            "result_limit",
            "presentation_mode",
            "requested_basemap",
            "required_data_sources",
            "required_tool_category",
            "tools_needed",
            "direct_response_sufficient",
            "expected_frontend_update",
            "atomic_tasks",
            "viewport_intent",
        )
        for field_name in inherited_fields:
            if field_name in latest_contract:
                payload[field_name] = latest_contract[field_name]

        previous_filters = json_object(latest_contract.get("filters"))
        current_filters = recovered.filters
        payload["filters"] = {**previous_filters, **current_filters}
        if recovered.result_limit is not None:
            payload["result_limit"] = recovered.result_limit

        previous_concepts = latest_contract.get("requested_concepts")
        if isinstance(previous_concepts, list):
            payload["requested_concepts"] = cls._dedupe(
                cls._string_values(previous_concepts)
                + list(recovered.requested_concepts)
            )
        previous_attributes = latest_contract.get("requested_attributes")
        if isinstance(previous_attributes, list):
            payload["requested_attributes"] = cls._dedupe(
                cls._string_values(previous_attributes)
                + list(recovered.requested_attributes)
            )

        previous_radius = latest_contract.get("radius_m")
        if recovered.radius_m is None and isinstance(previous_radius, (int, float)):
            payload["radius_m"] = previous_radius

        previous_map_target = latest_contract.get("map_target")
        if not recovered.map_target and isinstance(previous_map_target, str):
            payload["map_target"] = previous_map_target
        elif not recovered.map_target and recovered.location_signals:
            first_location = recovered.location_signals[0]
            payload["map_target"] = (
                first_location.normalized_value or first_location.raw_value
            )

        # The current turn has resolved the pending slot.  Pending parser
        # state and the old provider failure must not be replayed into the
        # capability resolver or completion evaluator.
        payload.update(
            {
                "user_text": recovered.user_text,
                "conversation_context": recovered.conversation_context,
                "location_signals": recovered.location_signals,
                "temporal_signal": recovered.temporal_signal,
                "relationship": "clarification",
                "ambiguities": [],
                "clarification_plan": None,
                "provider_error": recovered.provider_error,
                "failure_category": None,
                "requires_reparse": False,
            }
        )
        return TurnParseResult.model_validate(payload)

    # -------------------------------------------------------------------------
    @classmethod
    def _pending_field_kinds(cls, contract: dict[str, Any]) -> set[str]:
        clarification = contract.get("clarification_plan")
        fields = (
            clarification.get("blocking_fields")
            if is_json_object(clarification)
            else contract.get("ambiguities")
        )
        if not isinstance(fields, list):
            return set()
        kinds: set[str] = set()
        for value in cast(list[object], fields):
            field = str(value or "").strip().casefold().replace("-", "_")
            if not field:
                continue
            if "location" in field or field in {"place", "target"}:
                kinds.add("location")
            elif "time" in field or "temporal" in field:
                kinds.add("temporal")
            elif "radius" in field or "distance" in field:
                kinds.add("radius")
            elif any(
                token in field
                for token in ("threshold", "top_n", "result_limit", "magnitude")
            ):
                kinds.add("quantitative")
        return kinds

    # -------------------------------------------------------------------------
    @classmethod
    def _extract_bare_location_answer(
        cls,
        message: str,
        capability_catalog: list[dict[str, Any]] | None,
    ) -> LocationSignal | None:
        """Extract a short place answer only while a location slot is pending."""

        candidate = " ".join(str(message or "").strip().split())
        candidate = re.sub(
            r"^(?:use|choose|select|set(?:\s+the)?\s+location\s+to|"
            r"(?:the\s+)?location\s+is|i\s+mean)\s+",
            "",
            candidate,
            flags=re.IGNORECASE,
        )
        candidate = re.split(
            r"\s+(?:for|on|as)\s+(?:the\s+)?map\b",
            candidate,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        candidate = candidate.strip(" \t\r\n.,;:!?\"'")
        normalized = candidate.casefold()
        if (
            not candidate
            or normalized in cls._INVALID_LOCATION_VALUES
            or normalized in {"none", "unknown", "anywhere", "somewhere", "same place"}
            or " and " in f" {normalized} "
            or " or " in f" {normalized} "
            or len(candidate) > 80
            or len(candidate.split()) > 8
            or not any(character.isalpha() for character in candidate)
            or cls._extract_temporal_window(candidate) is not None
            or cls._extract_distance_m(candidate) is not None
        ):
            return None
        catalog_terms = cls._catalog_concepts(candidate, capability_catalog)
        if catalog_terms and " ".join(catalog_terms) == normalized:
            return None
        return LocationSignal(
            signal_type="address",
            raw_value=candidate,
            normalized_value=candidate,
            confidence=0.78,
            source="text",
        )

    # -------------------------------------------------------------------------
    @classmethod
    def _clarification_temporal_signal(
        cls,
        turn: TurnParseResult,
        user_message: str,
        *,
        latest_contract: dict[str, Any] | None = None,
    ) -> TemporalSignal | None:
        temporal = turn.temporal_signal
        window = cls._extract_temporal_window(user_message)
        if window:
            previous_temporal = (
                latest_contract.get("temporal_signal")
                if is_json_object(latest_contract)
                else None
            )
            previous_temporal = (
                previous_temporal if is_json_object(previous_temporal) else {}
            )
            previous_mode = str(previous_temporal.get("mode") or "").strip().casefold()
            mode = temporal.mode if temporal.mode != "none" else "current"
            if previous_mode in {"current", "historical", "forecast", "none"}:
                # A time-window answer completes the parent's pending slot. It
                # supplies boundaries, but does not turn the clarification into
                # a different temporal task mode based only on the model's
                # classification of the answer phrase.
                mode = cast(TemporalMode, previous_mode)
            if mode == "none":
                mode = "current"
            return temporal.model_copy(
                update={
                    "mode": mode,
                    "raw_text": window,
                    "reference_time_iso": None,
                    "start_time_iso": None,
                    "end_time_iso": None,
                }
            )
        if (
            temporal.raw_text
            or temporal.start_time_iso
            or temporal.end_time_iso
            or temporal.mode != "none"
        ):
            return temporal
        return None

    # -------------------------------------------------------------------------
    @classmethod
    def _pending_clarification_request(
        cls,
        *,
        user_message: str,
        conversation_messages: list[dict[str, Any]],
        capability_catalog: list[dict[str, Any]] | None,
        latest_contract: dict[str, Any] | None,
    ) -> str | None:
        """Return the prior user request when this turn fills a pending slot.

        A provider timeout can happen while parsing a clarification answer.  In
        that case the answer is intentionally not reinterpreted as a new task:
        the previous contract supplies the task and the current turn supplies
        the missing value.  The contract is used only when it records a pending
        clarification, so a completed task cannot leak into an unrelated turn.
        """

        contract = latest_contract if is_json_object(latest_contract) else None
        pending = cls._contract_needs_clarification(contract)
        prior_message = (
            str(contract.get("user_text") or "").strip()
            if contract is not None
            else ""
        )
        if not pending:
            assistant_content = cls._last_message_content(
                conversation_messages, role="assistant"
            )
            pending = cls._looks_like_clarification(assistant_content)

        if not pending:
            return None

        if not prior_message:
            for item in reversed(conversation_messages):
                if not is_json_object(item) or item.get("role") != "user":
                    continue
                candidate = str(item.get("content") or "").strip()
                if candidate and candidate != user_message.strip():
                    prior_message = candidate
                    break
        if not prior_message or not cls._contains_clarification_answer(
            user_message, capability_catalog
        ):
            return None
        return prior_message

    # -------------------------------------------------------------------------
    @staticmethod
    def _contract_needs_clarification(
        contract: dict[str, Any] | None,
    ) -> bool:
        if contract is None:
            return False
        if is_json_object(contract.get("clarification_plan")):
            return True
        if str(contract.get("expected_frontend_update") or "").casefold() == (
            "clarification"
        ):
            return True
        ambiguities = contract.get("ambiguities")
        return isinstance(ambiguities, list) and bool(cast(list[object], ambiguities))

    # -------------------------------------------------------------------------
    @classmethod
    def _contains_clarification_answer(
        cls,
        message: str,
        capability_catalog: list[dict[str, Any]] | None,
    ) -> bool:
        return bool(
            cls._extract_temporal_window(message)
            or cls._extract_distance_m(message) is not None
            or cls._extract_location_signal(message) is not None
            or cls._catalog_concepts(message, capability_catalog)
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _last_message_content(
        messages: list[dict[str, Any]], *, role: str
    ) -> str:
        for item in reversed(messages):
            if is_json_object(item) and item.get("role") == role:
                return str(item.get("content") or "").strip()
        return ""

    # -------------------------------------------------------------------------
    @staticmethod
    def _looks_like_clarification(message: str) -> bool:
        normalized = " ".join(message.casefold().split())
        return any(
            phrase in normalized
            for phrase in (
                "please specify",
                "please provide",
                "please select",
                "which ",
                "i need more information",
                "could not determine",
                "couldn't determine",
            )
        )

    # -------------------------------------------------------------------------
    @classmethod
    def _recovered_temporal_signal(
        cls,
        *,
        user_message: str,
        analysis_message: str,
        latest_contract: dict[str, Any] | None,
    ) -> TemporalSignal:
        window = cls._extract_temporal_window(user_message) or cls._extract_temporal_window(
            analysis_message
        )
        previous = latest_contract.get("temporal_signal") if latest_contract else None
        previous = previous if is_json_object(previous) else {}
        mode_text = str(previous.get("mode") or "").strip().casefold()
        if mode_text not in {"none", "current", "forecast", "historical"}:
            mode_text = ""
        if not mode_text:
            mode_text = "forecast" if re.search(
                r"\bforecast\b", analysis_message, re.IGNORECASE
            ) else "current"
        mode: TemporalMode = cast(TemporalMode, mode_text)
        granularity_text = str(previous.get("granularity") or "").strip().casefold()
        if granularity_text not in {
            "none",
            "instant",
            "hour",
            "day",
            "week",
            "month",
            "year",
        }:
            granularity_text = "instant"
        granularity: TemporalGranularity = cast(
            TemporalGranularity,
            "instant" if granularity_text == "week" else granularity_text,
        )
        aggregation_text = str(previous.get("aggregation") or "").strip().casefold()
        if aggregation_text not in {
            "none",
            "min",
            "max",
            "mean",
            "sum",
            "count",
            "latest",
        }:
            aggregation_text = "none"
        aggregation: TemporalAggregation = cast(
            TemporalAggregation,
            "none" if aggregation_text == "latest" else aggregation_text,
        )
        temporal_text = window or str(previous.get("raw_text") or "").strip() or None
        if temporal_text is None and re.search(r"\brecent\b", analysis_message, re.IGNORECASE):
            # Keep explicit recency visible to the canonical temporal compiler.
            # It must be clarified rather than silently downgraded to "current".
            temporal_text = "recent"
        return TemporalSignal(
            mode=mode,
            raw_text=temporal_text,
            reference_time_iso=(
                None
                if window
                else str(previous.get("reference_time_iso") or "").strip() or None
            ),
            start_time_iso=(
                None
                if window
                else str(previous.get("start_time_iso") or "").strip() or None
            ),
            end_time_iso=(
                None
                if window
                else str(previous.get("end_time_iso") or "").strip() or None
            ),
            granularity=granularity,
            aggregation=aggregation,
        )

    # -------------------------------------------------------------------------
    @classmethod
    def _extract_temporal_window(cls, message: str) -> str | None:
        match = cls._TEMPORAL_WINDOW_PATTERN.search(message)
        return match.group(0).strip() if match is not None else None

    # -------------------------------------------------------------------------
    @classmethod
    def _catalog_concepts(
        cls,
        message: str,
        capability_catalog: list[dict[str, Any]] | None,
    ) -> list[str]:
        """Extract only catalog-backed semantic terms for timeout recovery."""

        if not capability_catalog:
            return []
        query_tokens = {
            token
            for token in cls._token_forms(message)
            if token not in cls._CATALOG_STOPWORDS
        }
        if not query_tokens:
            return []
        concepts: list[str] = []
        for capability in capability_catalog:
            evidence_values = cls._catalog_evidence_values(capability)
            for evidence in evidence_values:
                for token in cls._token_forms(evidence):
                    if token in query_tokens and token not in cls._CATALOG_STOPWORDS:
                        concepts.append(token)
        return cls._ordered_concepts(message, cls._dedupe(concepts))

    # -------------------------------------------------------------------------
    @classmethod
    def _requires_catalog_distance(
        cls,
        *,
        message: str,
        attributes: list[str],
        catalog_concepts: list[str],
        capability_catalog: list[dict[str, Any]] | None,
        distance_m: float | None,
    ) -> bool:
        """Reject only requests whose matched capability requires a radius.

        ``around`` can describe a location context for a point/direct or
        raster capability, while ``near`` and ``within`` normally describe a
        distance-bounded feature search.  The distinction is resolved from
        the capability contract rather than from a provider, location, or
        phrase-specific exception.
        """

        if (
            distance_m is not None
            or not cls._PROXIMITY_PATTERN.search(message)
            or not any(item not in attributes for item in catalog_concepts)
        ):
            return False
        matches = cls._catalog_matches(message, capability_catalog)
        if not matches:
            return True
        relationship = (
            "distance"
            if cls._DISTANCE_DEPENDENT_PROXIMITY_PATTERN.search(message)
            else "context"
        )
        return not any(
            cls._supports_location_context_without_distance(
                capability,
                relationship=relationship,
            )
            for capability in matches
        )

    # -------------------------------------------------------------------------
    @classmethod
    def _catalog_matches(
        cls,
        message: str,
        capability_catalog: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        if not capability_catalog:
            return []
        query_tokens = {
            token
            for token in cls._token_forms(message)
            if token not in cls._CATALOG_STOPWORDS
        }
        if not query_tokens:
            return []
        matches: list[dict[str, Any]] = []
        for capability in capability_catalog:
            evidence_tokens = {
                token
                for evidence in cls._catalog_evidence_values(capability)
                for token in cls._token_forms(evidence)
                if token not in cls._CATALOG_STOPWORDS
            }
            if query_tokens.intersection(evidence_tokens):
                matches.append(capability)
        return matches

    # -------------------------------------------------------------------------
    @classmethod
    def _catalog_evidence_values(cls, capability: dict[str, Any]) -> list[str]:
        metadata = json_object(capability.get("metadata"))
        return [
            str(capability.get("name") or ""),
            str(capability.get("description") or ""),
            *cls._string_values(capability.get("capabilities")),
            *cls._string_values(metadata.get("keywords")),
            *cls._string_values(metadata.get("action_tags")),
            *cls._string_values(metadata.get("task_tags")),
            *cls._string_values(
                json_object(capability.get("agenticUse")).get("plannerHints")
            ),
        ]

    # -------------------------------------------------------------------------
    @classmethod
    def _supports_location_context_without_distance(
        cls,
        capability: dict[str, Any],
        *,
        relationship: str,
    ) -> bool:
        metadata = json_object(capability.get("metadata"))
        execution_contract = normalized_execution_contract(capability)
        supported_scopes = {
            str(item).strip().casefold()
            for item in cls._string_values(
                execution_contract.get("supported_scope_kinds")
            )
            if str(item).strip()
        }
        if relationship == "context" and supported_scopes.intersection(
            {"bbox", "point"}
        ):
            return True

        capability_type = str(capability.get("type") or "").strip().casefold()
        capability_kind = str(
            capability.get("capabilityKind") or capability.get("capability_kind") or ""
        ).strip().casefold()
        geometry_type = str(
            metadata.get("geometry_type")
            or capability.get("geometry_type")
            or ""
        ).strip().casefold()
        # The recovery catalog is already filtered to map-capable entries by
        # the orchestrator.  Standalone callers may still provide the flag;
        # absent metadata is therefore treated as unknown, not as disabled.
        supports_map = bool(
            capability.get("supports_map", metadata.get("supports_map", True))
        )
        queryable = bool(metadata.get("queryable", False))
        vectorizable = bool(metadata.get("vectorizable", False))

        if not supports_map or queryable or vectorizable:
            return False
        if capability_type in {"direct-tool", "direct_tool"}:
            return geometry_type in {"point", "not-applicable", "none", ""}
        if capability_kind in {"analysis-tool", "analysis_tool"}:
            return geometry_type in {
                "point",
                "not-applicable",
                "raster-grid",
                "raster_grid",
                "none",
                "",
            }
        return relationship == "context" and geometry_type in {
            "raster-grid",
            "raster_grid",
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def _token_forms(value: object) -> set[str]:
        tokens = {
            token.casefold()
            for token in re.findall(r"[a-z0-9]+", str(value or ""))
            if token
        }
        forms = set(tokens)
        for token in tokens:
            if len(token) > 3 and token.endswith("s"):
                forms.add(token[:-1])
        return forms

    # -------------------------------------------------------------------------
    @staticmethod
    def _string_values(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [
            str(item)
            for item in cast(list[object], value)
            if str(item).strip()
        ]

    # -------------------------------------------------------------------------
    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))

    # -------------------------------------------------------------------------
    @classmethod
    def _ordered_concepts(cls, message: str, concepts: list[str]) -> list[str]:
        """Keep the semantic order expressed by the user request."""

        attribute_patterns = dict(cls._ATTRIBUTE_PATTERNS)
        positions: dict[str, int] = {}
        for index, concept in enumerate(concepts):
            pattern = attribute_patterns.get(concept)
            match = pattern.search(message) if pattern is not None else None
            if match is not None:
                positions[concept] = match.start()
                continue
            token_positions = [
                match.start()
                for token in cls._token_forms(concept)
                for match in re.finditer(
                    rf"\b{re.escape(token)}s?\b", message, flags=re.IGNORECASE
                )
            ]
            positions[concept] = min(token_positions, default=len(message) + index)
        return sorted(concepts, key=lambda concept: positions[concept])

    # -------------------------------------------------------------------------
    @classmethod
    def _extract_distance_m(cls, message: str) -> float | None:
        match = cls._DISTANCE_PATTERN.search(message)
        if match is None:
            return None
        value = float(match.group("value"))
        unit = match.group("unit").casefold()
        multiplier = 1.0 if unit in {"m", "meter", "meters", "metre", "metres"} else 1_000.0
        if unit in {"mi", "mile", "miles"}:
            multiplier = 1_609.344
        return value * multiplier

    # -------------------------------------------------------------------------
    @classmethod
    def _extract_location_signal(cls, message: str) -> LocationSignal | None:
        coordinate_match = cls._COORDINATE_PATTERN.search(message)
        if coordinate_match is not None:
            latitude = float(coordinate_match.group("lat"))
            longitude = float(coordinate_match.group("lon"))
            if -90 <= latitude <= 90 and -180 <= longitude <= 180:
                raw_value = coordinate_match.group(0)
                return LocationSignal(
                    signal_type="coordinates",
                    raw_value=raw_value,
                    normalized_value=raw_value,
                    latitude=latitude,
                    longitude=longitude,
                    confidence=0.98,
                    source="text",
                )

        matches = list(cls._LOCATION_PATTERN.finditer(message))
        for match in reversed(matches):
            candidate = cls._clean_location(match.group("location"))
            if candidate is None:
                continue
            return LocationSignal(
                signal_type="city",
                raw_value=candidate,
                normalized_value=candidate,
                confidence=0.9,
                source="text",
            )
        return None

    # -------------------------------------------------------------------------
    @classmethod
    def _clean_location(cls, value: str) -> str | None:
        candidate = cls._LOCATION_TAIL_PATTERN.split(value, maxsplit=1)[0]
        candidate = " ".join(candidate.strip(" \'\"").split())
        normalized = candidate.casefold()
        if (
            not candidate
            or normalized in cls._INVALID_LOCATION_VALUES
            or " and " in f" {normalized} "
            or " or " in f" {normalized} "
            or len(candidate) > 80
            or len(candidate.split()) > 8
            or not any(character.isalpha() for character in candidate)
        ):
            return None
        return candidate

    # -------------------------------------------------------------------------
    @staticmethod
    def _normalize_recent_messages(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        return [
            {
                "role": str(item.get("role") or "unknown"),
                "content": str(item.get("content") or ""),
            }
            for item in messages[-8:]
            if is_json_object(item)
        ]

    # -------------------------------------------------------------------------
    @staticmethod
    def _active_basemap(memory_snapshot: dict[str, Any]) -> str | None:
        active = memory_snapshot.get("active_visualization")
        if not is_json_object(active):
            return None
        value = active.get("basemap_id")
        return value.strip() if isinstance(value, str) and value.strip() else None
