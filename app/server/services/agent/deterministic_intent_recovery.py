from __future__ import annotations

import re
from typing import Any

from server.common.typing import is_json_object
from server.contracts.extraction import (
    ContextQuery,
    ConversationContextSnapshot,
    LocationSignal,
    NormalizedAction,
    TemporalSignal,
    TurnParseResult,
    ViewportIntent,
)
from server.domain.agent.actions import AgentAction


###############################################################################
class DeterministicIntentRecoveryService:
    """Recover explicit location/data requests when structured parsing times out.

    This is deliberately a narrow language boundary.  It does not attempt to
    replace the model parser: a request must contain an explicit coordinate or
    place phrase and either a clear map verb or a catalog-recognizable data
    concept.  Ambiguous, deictic, and unsupported requests continue through
    the normal parser failure diagnostic.
    """

    RECOVERY_WARNING = (
        "Structured agent extraction timed out; the explicit location and "
        "catalog-backed data request was executed deterministically."
    )

    _COORDINATE_PATTERN = re.compile(
        r"(?P<lat>[+-]?\d{1,2}(?:\.\d+)?)\s*[,;]\s*"
        r"(?P<lon>[+-]?\d{1,3}(?:\.\d+)?)"
    )
    _LOCATION_PATTERN = re.compile(
        r"\b(?:in|near|around|at|over|of|for)\s+"
        r"(?P<location>[^?.!,;]+)",
        flags=re.IGNORECASE,
    )
    _LOCATION_TAIL_PATTERN = re.compile(
        r"\s+(?:with|showing|displaying|today|tomorrow|now|currently|please|"
        r"for\s+(?:today|tomorrow|now)|and\s+(?:the\s+)?(?:current\s+)?"
        r"(?:weather|forecast|air\s+quality|humidity|pressure|wind|"
        r"temperature|precipitation))\b",
        flags=re.IGNORECASE,
    )
    _MAP_LANGUAGE_PATTERN = re.compile(
        r"\b(?:map|on\s+(?:the\s+)?map|as\s+(?:a\s+)?map|"
        r"visuali[sz]e|plot|locate|find|center|centre|where\s+is)\b",
        flags=re.IGNORECASE,
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
    ) -> TurnParseResult | None:
        """Return a safe executable contract for a timed-out explicit request."""

        if str((provider_error or {}).get("code") or "").strip() != "provider_timeout":
            return None

        location = cls._extract_location_signal(user_message)
        if location is None:
            return None

        attributes = [
            label
            for label, pattern in cls._ATTRIBUTE_PATTERNS
            if pattern.search(user_message)
        ]
        if not attributes and not cls._MAP_LANGUAGE_PATTERN.search(user_message):
            return None

        map_request = bool(cls._MAP_LANGUAGE_PATTERN.search(user_message))

        concepts: list[str] = []
        if any(item in {"humidity", "pressure", "wind"} for item in attributes):
            # These measurements are served by one provider-backed catalog
            # overlay.  The resolver owns the final capability identity.
            concepts.append("humidity")
        if any(item in {"weather", "temperature", "precipitation"} for item in attributes):
            concepts.append("weather")
        if "air quality" in attributes:
            concepts.append("air quality")
        if "pm2.5" in attributes:
            concepts.append("pm2.5")

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
                "recovery": "explicit_catalog_request",
            }
        )

        return TurnParseResult(
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
            temporal_signal=TemporalSignal(
                mode="forecast" if re.search(r"\bforecast\b", user_message, re.IGNORECASE) else "current",
                granularity="instant",
            ),
            context_query=ContextQuery(kind="none"),
            parser_confidence=0.82,
            relationship="new_task",
            map_target=location.normalized_value or location.raw_value,
            requested_concepts=concepts,
            requested_attributes=attributes,
            presentation_mode="both" if map_request else "text",
            requested_basemap=cls._active_basemap(memory_snapshot) or "osm_default",
            tools_needed=True,
            direct_response_sufficient=False,
            expected_frontend_update="map_session" if map_request else "chat",
            viewport_intent=ViewportIntent(scope="auto"),
            provider_error=recovery_error,
            failure_category=None,
        )

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
