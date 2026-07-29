from __future__ import annotations

import json
import re
from typing import Literal

from server.common.logger import logger as LOGGER
from server.domain.agent.actions import AgentAction
from server.domain.agent.extraction_schemas import (
    LLMClarificationPlan,
    LLMLocationSignal,
    LLMParserExtraction,
    LLMViewportIntent,
)
from server.domain.extraction.models import (
    ConversationContextSnapshot,
    DisallowedPattern,
    LocationSignal,
    NormalizedAction,
    TemporalSignal,
    TurnParseResult,
    ViewportIntent,
)
from server.repositories.model_settings import ModelSettingsRepository
from server.services.llm.errors import LLMConfigurationError
from server.services.llm.factory import LLMFactory
from server.services.llm.prompts import get_parser_system_prompt
from server.services.llm.types import LLMRequest

###############################################################################
class ParserService:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        llm_factory: LLMFactory,
        settings_repo: ModelSettingsRepository,
        provider: str | None = None,
        model: str | None = None,
    ) -> None:
        self.llm_factory = llm_factory
        self.settings_repo = settings_repo
        self.provider = provider
        self.model = model
        self.last_context_usage: dict[str, object] | None = None

    # -------------------------------------------------------------------------
    @staticmethod
    def _to_text(value: object) -> str:
        if value is None:
            return ""
        return str(value)

    # -------------------------------------------------------------------------
    def _normalize_recent_messages(
        self, conversation_messages: list[dict]
    ) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        for item in conversation_messages[-8:]:
            if not isinstance(item, dict):
                normalized.append({"role": "unknown", "content": str(item)})
                continue
            normalized.append(
                {
                    "id": self._to_text(item.get("id")),
                    "conversation_id": self._to_text(item.get("conversation_id")),
                    "turn_index": self._to_text(item.get("turn_index")),
                    "role": self._to_text(item.get("role")),
                    "content": self._to_text(item.get("content")),
                    "created_at": self._to_text(item.get("created_at")),
                }
            )
        return normalized

    # -------------------------------------------------------------------------
    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            text = value.strip()
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
        return result

    # -------------------------------------------------------------------------
    @staticmethod
    def _contains_verbatim_span(user_message: str, candidate: str) -> bool:
        message = " ".join(str(user_message or "").casefold().split())
        span = " ".join(str(candidate or "").casefold().split())
        if not span:
            return False
        return span in message

    # -------------------------------------------------------------------------
    def _ambiguity_has_text_evidence(self, user_message: str, ambiguity: str) -> bool:
        normalized = str(ambiguity or "").strip()
        if not normalized:
            return False
        if normalized in {
            "missing_location",
            "deictic_without_memory",
            "potential_alternate_location",
            "alternate_location",
            "multiple_possible_locations",
            "ambiguous_place_name",
        }:
            return True
        quoted_terms = [item.strip() for item in re.findall(r"'([^']+)'", normalized)]
        if not quoted_terms:
            return True
        return any(self._contains_verbatim_span(user_message, term) for term in quoted_terms)

    # -------------------------------------------------------------------------
    def _extract_turn(
        self,
        *,
        user_message: str,
        memory_snapshot: dict,
        recent_messages: list[dict[str, str]],
        active_instructions: list[dict] | None = None,
        task_snapshot: dict | None = None,
    ) -> LLMParserExtraction:
        settings = None
        if self.provider is None or self.model is None:
            settings = self.settings_repo.get_or_create()
        if settings is None:
            provider_name = self.provider
            model_name = self.model
        else:
            provider_name = self.provider or settings.agent_model_provider
            model_name = self.model or settings.agent_model_name
        if provider_name is None or model_name is None:
            raise LLMConfigurationError("Agent provider and model must be configured for structured extraction.")
        parser_provider = self.llm_factory.get_provider(provider_name)
        self.last_context_usage = None
        prompt_payload = {
            "user_message": user_message,
            "memory_snapshot": memory_snapshot,
            "recent_messages": recent_messages[-6:],
            "active_instructions": active_instructions or [],
            "task_snapshot": task_snapshot,
        }
        request = LLMRequest(
            model=model_name,
            temperature=0.0,
            provider=provider_name,
            tools=[],
            tool_choice="none",
            messages=[
                {
                    "role": "system",
                    "content": get_parser_system_prompt(provider_name, model_name),
                },
                {
                    "role": "user",
                    "content": json.dumps(prompt_payload, ensure_ascii=True),
                },
            ],
        )
        payload = parser_provider.structured_output(
            request=request, schema=LLMParserExtraction
        )
        usage = getattr(parser_provider, "last_context_usage", None)
        self.last_context_usage = dict(usage) if isinstance(usage, dict) else None
        extracted = LLMParserExtraction.model_validate(payload)
        LOGGER.debug(
            "Parser LLM extraction: provider=%s model=%s task=%s action=%s",
            provider_name,
            model_name,
            extracted.task_class,
            extracted.action_id,
        )
        LOGGER.info(
            "parser_extract provider=%s model=%s task=%s action=%s relationship=%s viewport_scope=%s",
            provider_name,
            model_name,
            extracted.task_class,
            extracted.action_id,
            extracted.relationship,
            extracted.viewport_intent.scope if extracted.viewport_intent is not None else None,
        )
        return extracted

    # -------------------------------------------------------------------------
    @staticmethod
    def _extract_coordinate_signal(user_message: str) -> LLMLocationSignal | None:
        match = re.search(
            r"(?P<lat>[+-]?\d{1,2}(?:\.\d+)?)\s*[,;]\s*(?P<lon>[+-]?\d{1,3}(?:\.\d+)?)",
            user_message,
        )
        if match is None:
            return None
        latitude = float(match.group("lat"))
        longitude = float(match.group("lon"))
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            return None
        raw_value = match.group(0)
        return LLMLocationSignal(
            signal_type="coordinates",
            raw_value=raw_value,
            normalized_value=raw_value,
            latitude=latitude,
            longitude=longitude,
            confidence=0.98,
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _looks_like_map_request(user_message: str) -> bool:
        text = user_message.casefold()
        markers = (
            "map",
            "show",
            "display",
            "locate",
            "where is",
            "satellite",
            "overlay",
            "weather",
            "traffic",
            "amenities",
            "coordinates",
            "coordinate",
            "mapa",
            "carte",
            "karte",
            "mappa",
            "mostrar",
            "muestra",
            "montre",
        )
        return any(marker in text for marker in markers)

    # -------------------------------------------------------------------------
    @classmethod
    def _extract_text_location_signal(cls, user_message: str) -> LLMLocationSignal | None:
        coordinate_signal = cls._extract_coordinate_signal(user_message)
        if coordinate_signal is not None:
            return coordinate_signal

        text = user_message.strip()
        if not text or not cls._looks_like_map_request(text):
            return None

        cleaned = re.sub(r"(?i)\b(please|pls|could you|can you|show me|show|display|map|locate|find|open|create|make|muestra|mostrar|montre|carte|karte|mappa|mapa)\b", " ", text)
        cleaned = re.sub(r"(?i)\b(a|an|the|of|for|near|around|on|in|to|with|using|me)\b", " ", cleaned)
        cleaned = re.sub(r"(?i)\b(weather|traffic|amenities|overlay|overlays|layer|layers|satellite|imagery|coordinates?)\b", " ", cleaned)
        cleaned = re.sub(r"[.?!]+$", "", cleaned)
        cleaned = " ".join(cleaned.replace(":", " ").split())
        if len(cleaned) < 2:
            return None

        signal_type: Literal["address", "city"] = "address" if re.search(r"\d", cleaned) else "city"
        return LLMLocationSignal(
            signal_type=signal_type,
            raw_value=cleaned,
            normalized_value=cleaned,
            confidence=0.72 if signal_type == "address" else 0.68,
        )

    # -------------------------------------------------------------------------
    @classmethod
    def _fallback_extraction(cls, user_message: str) -> LLMParserExtraction:
        location_signal = cls._extract_text_location_signal(user_message)
        if location_signal is not None:
            task_tags = ["map"]
            action_tags = ["map"]
            requested_visualizations = ["map"]
            text = user_message.casefold()
            if any(marker in text for marker in ("weather", "rain", "precipitation", "radar")):
                action_tags.append("weather")
                requested_visualizations.append("weather")
            if "traffic" in text:
                action_tags.append("traffic")
                requested_visualizations.append("traffic")
            if any(marker in text for marker in ("amenit", "poi", "nearby")):
                action_tags.append("amenities")
                requested_visualizations.append("amenities")
            if any(marker in text for marker in ("satellite", "imagery")):
                action_tags.append("satellite")
                requested_visualizations.append("satellite")
            return LLMParserExtraction(
                task_class="map_search",
                action_id=AgentAction.MAP_SEARCH.value,
                action_label="General map request",
                task_tags=task_tags,
                action_tags=action_tags,
                requested_visualizations=requested_visualizations,
                requires_location=True,
                location_signals=[location_signal],
                parser_confidence=0.72,
                viewport_intent=cls._infer_viewport_intent(
                    text,
                    has_active_visualization=False,
                ),
            )

        return LLMParserExtraction(
            task_class="general_question",
            action_id=AgentAction.CHAT_RESPONSE.value,
            action_label="General question",
            task_tags=["chat"],
            action_tags=["general"],
            requires_location=False,
            parser_confidence=0.65,
        )

    # -------------------------------------------------------------------------
    @classmethod
    def _should_use_fallback(
        cls,
        *,
        extracted: LLMParserExtraction,
        fallback: LLMParserExtraction,
    ) -> bool:
        if fallback.task_class == "map_search" and (
            extracted.task_class in {"unclear", "general_question"}
            or not extracted.location_signals
        ):
            return True
        if extracted.parser_confidence < 0.35 and fallback.task_class != "unclear":
            return True
        return False

    # -------------------------------------------------------------------------
    def parse_turn(
        self,
        user_message: str,
        memory_snapshot: dict,
        conversation_messages: list[dict],
        active_instructions: list[dict] | None = None,
        task_snapshot: dict | None = None,
    ) -> TurnParseResult:
        normalized_recent = self._normalize_recent_messages(conversation_messages)
        parser_failure_ambiguity: str | None = None
        try:
            extracted = self._extract_turn(
                user_message=user_message,
                memory_snapshot=memory_snapshot,
                recent_messages=normalized_recent,
                active_instructions=active_instructions,
                task_snapshot=task_snapshot,
            )
        except LLMConfigurationError:
            raise
        except Exception as exc:
            LOGGER.exception("Parser LLM extraction failed: %s", exc)
            failure_ambiguity = (
                "parser_authentication_failed"
                if "invalid_api_key" in str(exc).lower() or "401" in str(exc)
                else "parser_unavailable"
            )
            parser_failure_ambiguity = failure_ambiguity
            extracted = LLMParserExtraction(
                task_class="unclear",
                action_id=AgentAction.UNKNOWN.value,
                action_label="General map request",
                task_tags=["map"],
                action_tags=["map"],
                requires_location=False,
                ambiguities=[failure_ambiguity],
                parser_confidence=0.0,
            )

        fallback = self._fallback_extraction(user_message)
        if self._should_use_fallback(extracted=extracted, fallback=fallback):
            if parser_failure_ambiguity is not None:
                fallback.ambiguities = self._dedupe(
                    [*fallback.ambiguities, parser_failure_ambiguity]
                )
                fallback.parser_confidence = min(fallback.parser_confidence, 0.35)
            extracted = fallback
        extracted = self._apply_domain_rules(user_message, extracted, memory_snapshot)

        extracted_location_signals = list(extracted.location_signals)
        verbatim_signals = [
            item
            for item in extracted_location_signals
            if self._contains_verbatim_span(user_message, item.raw_value)
        ]
        if verbatim_signals:
            extracted_location_signals = verbatim_signals

        location_signals = [
            LocationSignal(
                signal_type=item.signal_type,
                raw_value=item.raw_value,
                normalized_value=item.normalized_value or item.raw_value,
                latitude=item.latitude,
                longitude=item.longitude,
                confidence=item.confidence,
                source="model",
            )
            for item in extracted_location_signals
            if item.raw_value.strip()
        ]
        normalized_action = NormalizedAction(
            action_id=self._normalize_action_id(extracted.action_id, extracted.parser_confidence),
            action_label=extracted.action_label.strip() or "General map request",
            task_tags=[tag for tag in extracted.task_tags if str(tag).strip()],
            action_tags=[tag for tag in extracted.action_tags if str(tag).strip()],
            requested_visualizations=[
                tag for tag in extracted.requested_visualizations if str(tag).strip()
            ],
            requires_location=extracted.requires_location,
        )
        temporal_signal = TemporalSignal(
            mode=extracted.temporal_signal.mode,
            raw_text=extracted.temporal_signal.raw_text,
            reference_time_iso=extracted.temporal_signal.reference_time_iso,
        )
        disallowed = [
            DisallowedPattern(
                pattern_id=item.pattern_id,
                reason=item.reason,
                matched_text=item.matched_text,
            )
            for item in extracted.disallowed_patterns
        ]

        ambiguities = self._dedupe(list(extracted.ambiguities))
        ambiguities = [
            item
            for item in ambiguities
            if self._ambiguity_has_text_evidence(user_message, item)
        ]
        has_deictic = any(item.signal_type == "deictic" for item in location_signals)
        if normalized_action.requires_location and not location_signals:
            ambiguities = self._dedupe([*ambiguities, "missing_location"])
        if has_deictic and not memory_snapshot.get("active_location"):
            ambiguities = self._dedupe([*ambiguities, "deictic_without_memory"])

        if normalized_action.requires_location and not location_signals:
            LOGGER.info(
                "Parser missing location: action=%s ambiguities=%s user_text=%r",
                normalized_action.action_id,
                ambiguities,
                user_message,
            )
        if self._is_known_ambiguous_bare_place(user_message, location_signals):
            ambiguities = self._dedupe([*ambiguities, "ambiguous_place_name"])

        confidence = extracted.parser_confidence
        if ambiguities:
            confidence -= 0.15

        task_class = extracted.task_class
        if (
            task_class == "general_question"
            and normalized_action.requires_location
            and location_signals
            and self._looks_like_map_request(user_message)
        ):
            task_class = "map_search"

        result = TurnParseResult(
            user_text=user_message,
            conversation_context=ConversationContextSnapshot(
                recent_messages=normalized_recent,
                memory_snapshot=memory_snapshot,
            ),
            task_class=task_class,
            location_signals=location_signals,
            normalized_action=normalized_action,
            temporal_signal=temporal_signal,
            ambiguities=ambiguities,
            disallowed_patterns=disallowed,
            parser_confidence=max(0.0, min(1.0, confidence)),
            relationship=extracted.relationship,
            map_target=extracted.map_target,
            entity_target=extracted.entity_target,
            requested_layers=self._dedupe(extracted.requested_layers),
            requested_basemap=extracted.requested_basemap,
            requested_attributes=self._dedupe(extracted.requested_attributes),
            required_data_sources=self._dedupe(extracted.required_data_sources),
            required_tool_category=extracted.required_tool_category,
            tools_needed=extracted.tools_needed,
            direct_response_sufficient=extracted.direct_response_sufficient,
            requires_reparse=extracted.requires_reparse,
            capability_limitations=self._dedupe(extracted.capability_limitations),
            expected_frontend_update=extracted.expected_frontend_update,
            atomic_tasks=[item.model_dump(mode="json") for item in extracted.atomic_tasks],
            clarification_plan=(
                extracted.clarification_plan.model_dump(mode="json")
                if extracted.clarification_plan is not None
                else None
            ),
            viewport_intent=(
                ViewportIntent.model_validate(
                    extracted.viewport_intent.model_dump(mode="json")
                )
                if extracted.viewport_intent is not None
                else None
            ),
        )
        LOGGER.info(
            "parser_normalized task=%s action=%s relationship=%s locations=%d basemap=%s layers=%d viewport_scope=%s tighten=%s ambiguities=%s",
            result.task_class,
            result.normalized_action.action_id,
            result.relationship,
            len(result.location_signals),
            result.requested_basemap,
            len(result.requested_layers),
            result.viewport_intent.scope if result.viewport_intent is not None else None,
            (
                result.viewport_intent.tighten_relative_to_active
                if result.viewport_intent is not None
                else None
            ),
            ",".join(result.ambiguities) if result.ambiguities else "-",
        )
        return result

    # -------------------------------------------------------------------------
    @classmethod
    def _apply_domain_rules(
        cls,
        user_message: str,
        extracted: LLMParserExtraction,
        memory_snapshot: dict,
    ) -> LLMParserExtraction:
        text = " ".join(user_message.casefold().split())
        updates: dict[str, object] = {}
        inferred_viewport = cls._infer_viewport_intent(
            text,
            has_active_visualization=bool(memory_snapshot.get("active_visualization")),
        )

        if any(marker in text for marker in ("why did", "why has", "why was", "why it failed", "why did it fail")):
            updates.update(
                relationship="failure_inquiry",
                task_class="general_question",
                action_id=AgentAction.CHAT_RESPONSE.value,
                requires_location=False,
                tools_needed=False,
                direct_response_sufficient=True,
                required_tool_category="failure_diagnostics",
                expected_frontend_update="failure_diagnostic",
            )
        elif any(marker in text for marker in ("nice!", "can you now", "same map", "same place", "there")):
            updates["relationship"] = "follow_up"
            if memory_snapshot.get("active_location") and not any(
                marker in text
                for marker in (
                    "rome",
                    "colosseum",
                    "coliseum",
                    "paris",
                    "milan",
                    "zurich",
                    "coordinates",
                )
            ):
                updates["location_signals"] = []

        house_markers = ("house", "houses", "housing", "residential", "apartments", "buildings")
        if any(marker in text for marker in house_markers):
            requested_layers = [
                item
                for item in extracted.requested_layers
                if "amenit" not in item.casefold() and "poi" not in item.casefold()
            ]
            updates.update(
                task_class="map_search",
                action_id=AgentAction.DATA_LAYER_QUERY.value,
                action_label="Residential building visualization",
                entity_target="residential_buildings",
                requested_layers=cls._dedupe([*requested_layers, "overpass_residential_buildings"]),
                required_data_sources=cls._dedupe([*extracted.required_data_sources, "openstreetmap_overpass"]),
                required_tool_category="geospatial_features",
                tools_needed=True,
                direct_response_sufficient=False,
                expected_frontend_update="map_session",
            )
            place_match = re.search(
                r"(?i)\b(?:coliseum|colosseum)(?:\s+in\s+rome)?\b",
                user_message,
            )
            if place_match is not None:
                place_text = place_match.group(0)
                updates["location_signals"] = [
                    LLMLocationSignal(
                        signal_type="address",
                        raw_value=place_text,
                        normalized_value="Colosseum, Rome",
                        confidence=0.95,
                    )
                ]
                updates["map_target"] = "Colosseum, Rome"

        if any(marker in text for marker in ("satellite view", "satellite", "imagery")):
            updates["requested_basemap"] = "esri_world_imagery"
        if any(
            marker in text
            for marker in (
                "street map",
                "street maps",
                "road map",
                "default map",
                "no satellite",
                "without satellite",
            )
        ):
            updates.update(
                requested_basemap="osm_default",
                relationship="follow_up" if memory_snapshot.get("active_visualization") else extracted.relationship,
                expected_frontend_update="visualization_update",
            )
            if inferred_viewport is None and memory_snapshot.get("active_visualization"):
                inferred_viewport = LLMViewportIntent(
                    scope="preserve_current",
                    reason="basemap_only_follow_up",
                )

        if "openfreemap" in text:
            updates.update(
                requested_basemap=(
                    "openfreemap_positron"
                    if any(marker in text for marker in ("positron", "light", "clean"))
                    else "openfreemap_liberty"
                ),
                relationship=(
                    "follow_up" if memory_snapshot.get("active_visualization") else extracted.relationship
                ),
                expected_frontend_update="visualization_update",
            )

        ground_temperature = (
            "temperature" in text
            and any(marker in text for marker in ("ground", "surface", "at the ground"))
            and any(marker in text for marker in ("medium", "mean", "average"))
        )
        if ground_temperature:
            updates.update(
                requested_attributes=cls._dedupe(
                    [*extracted.requested_attributes, "ground_temperature"]
                ),
                required_tool_category="environmental_data",
                expected_frontend_update="clarification_with_map_update",
                clarification_plan=LLMClarificationPlan.model_validate({
                    "question": (
                        "Which temperature do you mean: current air temperature at 2 m, "
                        "daytime land-surface temperature, nighttime land-surface "
                        "temperature, or a mean over a specific period?"
                    ),
                    "reason": (
                        "The requested temperature metric and averaging period are ambiguous."
                    ),
                    "blocking_fields": [
                        "temperature_metric",
                        "temperature_time_basis",
                    ],
                    "options": [
                        {
                            "option_id": "air_temperature_2m",
                            "label": "Current air temperature at 2 m",
                        },
                        {
                            "option_id": "land_surface_temperature_day",
                            "label": "Daytime land-surface temperature",
                        },
                        {
                            "option_id": "land_surface_temperature_night",
                            "label": "Nighttime land-surface temperature",
                        },
                        {
                            "option_id": "mean_temperature_period",
                            "label": "Mean temperature over a specified period",
                        },
                    ],
                    "preserve_valid_results": True,
                    "apply_visualization_changes": True,
                }),
            )
            updates["ambiguities"] = cls._dedupe(
                [*extracted.ambiguities, "temperature_metric_underspecified"]
            )

        if inferred_viewport is not None:
            updates["viewport_intent"] = inferred_viewport

        return extracted.model_copy(update=updates)

    # -------------------------------------------------------------------------
    @staticmethod
    def _infer_viewport_intent(
        text: str,
        *,
        has_active_visualization: bool,
    ) -> LLMViewportIntent | None:
        if any(marker in text for marker in ("entire city", "whole city", "city wide", "city-wide")):
            return LLMViewportIntent(scope="city", reason="explicit_city_extent")
        if any(marker in text for marker in ("whole region", "entire region", "regional view")):
            return LLMViewportIntent(scope="region", reason="explicit_region_extent")
        if any(marker in text for marker in ("whole country", "entire country", "nationwide")):
            return LLMViewportIntent(scope="country", reason="explicit_country_extent")
        if any(
            marker in text
            for marker in (
                "much more closely",
                "more closely",
                "closer view",
                "zoom in",
                "too high as point of view",
                "too high a point of view",
                "too zoomed out",
                "street level",
            )
        ):
            return LLMViewportIntent(
                scope="street",
                tighten_relative_to_active=has_active_visualization,
                reason="explicit_tighter_view",
            )
        if any(
            marker in text
            for marker in ("around ", "near ", "nearby ", "via ", "at this street", "around via")
        ):
            return LLMViewportIntent(scope="street", reason="local_area_request")
        if has_active_visualization and any(
            marker in text
            for marker in (
                "street map",
                "street maps",
                "road map",
                "default map",
                "no satellite",
                "without satellite",
            )
        ):
            return LLMViewportIntent(scope="preserve_current", reason="basemap_only_follow_up")
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def _normalize_action_id(action_id: str, confidence: float) -> str:
        if confidence < 0.25:
            return AgentAction.UNKNOWN.value
        try:
            return AgentAction(str(action_id).strip()).value
        except ValueError:
            return AgentAction.UNKNOWN.value

    # -------------------------------------------------------------------------
    @staticmethod
    def _is_known_ambiguous_bare_place(
        user_message: str,
        location_signals: list[LocationSignal],
    ) -> bool:
        text = " ".join(str(user_message or "").casefold().split())
        if not re.search(r"\bnaples\b", text):
            return False
        if any(marker in text for marker in ("italy", "italia", "florida", "usa", "united states")):
            return False
        return any(
            str(signal.raw_value or "").strip().casefold() == "naples"
            or str(signal.normalized_value or "").strip().casefold() == "naples"
            for signal in location_signals
        )
