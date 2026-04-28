from __future__ import annotations

import json
import logging
import re
from typing import Literal

from AEGIS.server.domain.extraction.models import (
    ConversationContextSnapshot,
    DisallowedPattern,
    LocationSignal,
    NormalizedIntent,
    TemporalSignal,
    TurnParseResult,
)
from AEGIS.server.repositories.model_settings import ModelSettingsRepository
from AEGIS.server.services.llm.errors import LLMConfigurationError
from AEGIS.server.services.llm.factory import LLMFactory
from AEGIS.server.services.llm.types import LLMRequest
from pydantic import BaseModel, ConfigDict, Field

LOGGER = logging.getLogger(__name__)

PARSER_SYSTEM_PROMPT = """
Role:
You are the AEGIS parser. Extract turn-routing intent from the current user message.

Output:
Return JSON only with this schema:
- task_class: map_search|direct_query|general_question|unclear
- intent_id: short snake_case id
- intent_label: short human label
- task_tags: array of tags
- intent_tags: array of tags
- requested_visualizations: array of explicit requested map concepts such as satellite, terrain, air_quality, precipitation, poi, traffic, elevation, land_cover, active_fire
- requires_location: boolean
- location_signals: array of {signal_type,address/city/country/coordinates/deictic, raw_value, normalized_value, latitude, longitude, confidence}
- temporal_signal: {mode: current|historical|forecast|none, raw_text, reference_time_iso}
- ambiguities: array of strings
- disallowed_patterns: array of {pattern_id, reason, matched_text}
- parser_confidence: 0..1

Rules:
1. Always infer location entities from natural language when present.
2. If a location is explicitly present in user text, do not mark missing_location.
3. Keep extraction concise and deterministic; no prose.
4. The user may write in any language; interpret multilingual input without assuming English.
5. For each location_signals item, raw_value must be a verbatim span from the current user message.
6. Do not invent extra locations that are not explicitly present in the current user message.
7. requested_visualizations must use only canonical ids when relevant:
   satellite, terrain, air_quality, precipitation, poi, traffic, elevation, land_cover, active_fire, weather, aerosol, ozone, solar, noise
8. When the request is for air quality, prefer air_quality in requested_visualizations and intent tags unless the user explicitly requests another theme.
""".strip()


class _LLMTemporalSignal(BaseModel):
    model_config = ConfigDict(extra="ignore")

    mode: Literal["current", "historical", "forecast", "none"] = "none"
    raw_text: str | None = None
    reference_time_iso: str | None = None


class _LLMLocationSignal(BaseModel):
    model_config = ConfigDict(extra="ignore")

    signal_type: Literal["address", "city", "country", "coordinates", "deictic"] = (
        "address"
    )
    raw_value: str = ""
    normalized_value: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class _LLMDisallowedPattern(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pattern_id: str
    reason: str
    matched_text: str


class _LLMParserExtraction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    task_class: Literal["map_search", "direct_query", "general_question", "unclear"] = (
        "unclear"
    )
    intent_id: str = "general_map"
    intent_label: str = "General map request"
    task_tags: list[str] = Field(default_factory=list)
    intent_tags: list[str] = Field(default_factory=list)
    requested_visualizations: list[str] = Field(default_factory=list)
    requires_location: bool = True
    location_signals: list[_LLMLocationSignal] = Field(default_factory=list)
    temporal_signal: _LLMTemporalSignal = Field(default_factory=_LLMTemporalSignal)
    ambiguities: list[str] = Field(default_factory=list)
    disallowed_patterns: list[_LLMDisallowedPattern] = Field(default_factory=list)
    parser_confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class ParserService:
    def __init__(
        self,
        *,
        llm_factory: LLMFactory | None = None,
        settings_repo: ModelSettingsRepository | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> None:
        self.llm_factory = llm_factory or LLMFactory()
        self.settings_repo = settings_repo or ModelSettingsRepository()
        self.provider = provider
        self.model = model
        self.last_context_usage: dict[str, object] | None = None

    @staticmethod
    def _to_text(value: object) -> str:
        if value is None:
            return ""
        return str(value)

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
                    "session_id": self._to_text(item.get("session_id")),
                    "turn_index": self._to_text(item.get("turn_index")),
                    "role": self._to_text(item.get("role")),
                    "content": self._to_text(item.get("content")),
                    "created_at": self._to_text(item.get("created_at")),
                }
            )
        return normalized

    def _dedupe(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            text = value.strip()
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
        return result

    @staticmethod
    def _contains_verbatim_span(user_message: str, candidate: str) -> bool:
        message = " ".join(str(user_message or "").casefold().split())
        span = " ".join(str(candidate or "").casefold().split())
        if not span:
            return False
        return span in message

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
        }:
            return True
        quoted_terms = [item.strip() for item in re.findall(r"'([^']+)'", normalized)]
        if not quoted_terms:
            return True
        return any(self._contains_verbatim_span(user_message, term) for term in quoted_terms)

    def _extract_turn(self, *, user_message: str, memory_snapshot: dict, recent_messages: list[dict[str, str]]) -> _LLMParserExtraction:
        settings = self.settings_repo.get_or_create()
        provider_name = self.provider or settings.parser_model_provider
        model_name = self.model or settings.parser_model_name
        parser_provider = self.llm_factory.get_parser_provider(provider_name)
        self.last_context_usage = None
        prompt_payload = {
            "user_message": user_message,
            "memory_snapshot": memory_snapshot,
            "recent_messages": recent_messages[-6:],
        }
        request = LLMRequest(
            model=model_name,
            temperature=0.0,
            provider=provider_name,
            messages=[
                {"role": "system", "content": PARSER_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(prompt_payload, ensure_ascii=True),
                },
            ],
        )
        payload = parser_provider.structured_output(
            request=request, schema=_LLMParserExtraction
        )
        usage = getattr(parser_provider, "last_context_usage", None)
        self.last_context_usage = dict(usage) if isinstance(usage, dict) else None
        extracted = _LLMParserExtraction.model_validate(payload)
        LOGGER.debug(
            "Parser LLM extraction: provider=%s model=%s task=%s intent=%s",
            provider_name,
            model_name,
            extracted.task_class,
            extracted.intent_id,
        )
        return extracted

    def _fallback_location_signals(self, user_message: str) -> list[LocationSignal]:
        pattern = re.compile(
            r"\b(?:around|near|over|above|in|for)\s+"
            r"([A-Z][A-Za-zÀ-ÖØ-öø-ÿ.'-]*(?:\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ.'-]*){0,3})"
        )
        stop_words = {
            "I",
            "Show",
            "Map",
            "Just",
            "The",
            "A",
            "An",
            "Where",
            "Right",
            "Now",
        }
        signals: list[LocationSignal] = []
        for match in pattern.finditer(user_message):
            raw_value = match.group(1).strip(" .,!?")
            if not raw_value or raw_value in stop_words:
                continue
            signals.append(
                LocationSignal(
                    signal_type="address",
                    raw_value=raw_value,
                    normalized_value=raw_value,
                    confidence=0.55,
                    source="heuristic",
                )
            )
            break
        return signals

    def parse_turn(
        self,
        user_message: str,
        memory_snapshot: dict,
        conversation_messages: list[dict],
    ) -> TurnParseResult:
        normalized_recent = self._normalize_recent_messages(conversation_messages)
        try:
            extracted = self._extract_turn(
                user_message=user_message,
                memory_snapshot=memory_snapshot,
                recent_messages=normalized_recent,
            )
        except LLMConfigurationError:
            raise
        except Exception as exc:
            LOGGER.exception("Parser LLM extraction failed: %s", exc)
            extracted = _LLMParserExtraction(
                task_class="unclear",
                intent_id="general_map",
                intent_label="General map request",
                task_tags=["map"],
                intent_tags=["map"],
                requires_location=False,
                ambiguities=["parser_unavailable"],
                parser_confidence=0.0,
            )

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
        if not location_signals:
            location_signals = self._fallback_location_signals(user_message)
        normalized_intent = NormalizedIntent(
            intent_id=extracted.intent_id.strip() or "general_map",
            intent_label=extracted.intent_label.strip() or "General map request",
            task_tags=[tag for tag in extracted.task_tags if str(tag).strip()],
            intent_tags=[tag for tag in extracted.intent_tags if str(tag).strip()],
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
        if normalized_intent.requires_location and not location_signals:
            ambiguities = self._dedupe([*ambiguities, "missing_location"])
        if has_deictic and not memory_snapshot.get("active_location"):
            ambiguities = self._dedupe([*ambiguities, "deictic_without_memory"])

        if normalized_intent.requires_location and not location_signals:
            LOGGER.info(
                "Parser missing location: intent=%s ambiguities=%s user_text=%r",
                normalized_intent.intent_id,
                ambiguities,
                user_message,
            )

        confidence = extracted.parser_confidence
        if ambiguities:
            confidence -= 0.15

        return TurnParseResult(
            user_text=user_message,
            conversation_context=ConversationContextSnapshot(
                recent_messages=normalized_recent,
                memory_snapshot=memory_snapshot,
            ),
            task_class=extracted.task_class,
            location_signals=location_signals,
            normalized_intent=normalized_intent,
            temporal_signal=temporal_signal,
            ambiguities=ambiguities,
            disallowed_patterns=disallowed,
            parser_confidence=max(0.0, min(1.0, confidence)),
        )
