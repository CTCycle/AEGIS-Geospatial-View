from __future__ import annotations

from typing import Any

from server.common.typing import is_json_object

import json
import re
from typing import Literal, cast

from server.common.logger import logger as LOGGER
from server.domain.agent.actions import AgentAction
from server.domain.agent.extraction_schemas import (
    LLMLocationSignal,
    LLMParserExtraction,
)
from server.contracts.extraction import (
    ConversationContextSnapshot,
    ContextQuery,
    DisallowedPattern,
    LocationSignal,
    NormalizedAction,
    OverlayCommand,
    TemporalSignal,
    TurnParseResult,
    ViewportIntent,
)
from server.repositories.model_settings import ModelSettingsRepository
from server.services.llm.errors import (
    LLMConfigurationError,
    LLMProviderRequestError,
    LLMResponseParsingError,
    LLMStructuredOutputError,
)
from server.services.llm.factory import LLMFactory
from server.prompts.parser import build_parser_prompt
from server.services.llm.types import LLMRequest
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.runtime_registry import RuntimeRegistry


###############################################################################
class ParserService:
    _FAILURE_CATEGORIES = frozenset(
        {
            "model_capability",
            "provider_api",
            "schema_definition",
            "response_parsing",
            "context_limit",
        }
    )

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        llm_factory: LLMFactory,
        settings_repo: ModelSettingsRepository,
        provider: str | None = None,
        model: str | None = None,
        capability_registry: CapabilityRegistry | None = None,
        runtime_registry: RuntimeRegistry | None = None,
    ) -> None:
        self.llm_factory = llm_factory
        self.settings_repo = settings_repo
        self.provider = provider
        self.model = model
        self.capability_registry = capability_registry
        self.runtime_registry = runtime_registry
        self.last_context_usage: dict[str, object] | None = None

    # -------------------------------------------------------------------------
    @staticmethod
    def _to_text(value: object) -> str:
        if value is None:
            return ""
        return str(value)

    # -------------------------------------------------------------------------
    @staticmethod
    def _normalize_recent_messages(
        conversation_messages: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        for item in conversation_messages[-8:]:
            if not is_json_object(item):
                normalized.append({"role": "unknown", "content": str(item)})
                continue
            normalized.append(
                {
                    "id": ParserService._to_text(item.get("id")),
                    "conversation_id": ParserService._to_text(
                        item.get("conversation_id")
                    ),
                    "turn_index": ParserService._to_text(item.get("turn_index")),
                    "role": ParserService._to_text(item.get("role")),
                    "content": ParserService._to_text(item.get("content")),
                    "created_at": ParserService._to_text(item.get("created_at")),
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
    def _catalog_evidence(self) -> list[dict[str, Any]]:
        """Expose executable catalog identity to the structured parser."""
        if self.capability_registry is None:
            return []
        collections = (
            self.capability_registry.list_basemaps(),
            self.capability_registry.list_overlays(),
            self.capability_registry.list_cameras(),
            self.capability_registry.list_transit(),
            self.capability_registry.list_tools(),
        )
        evidence: list[dict[str, Any]] = []
        for collection in collections:
            for capability in collection:
                capability_id = str(capability.get("id") or "").strip()
                if not capability_id:
                    continue
                if (
                    self.runtime_registry is not None
                    and not self.runtime_registry.is_enabled(capability_id)
                ):
                    continue
                metadata = capability.get("metadata")
                metadata = metadata if is_json_object(metadata) else {}
                evidence.append(
                    {
                        "id": capability_id,
                        "label": str(
                            metadata.get("label")
                            or capability.get("name")
                            or capability_id
                        ),
                        "capability_kind": capability.get("capabilityKind"),
                        "rendering_mode": capability.get("renderingMode"),
                        "capabilities": list(capability.get("capabilities") or []),
                        "keywords": list(metadata.get("keywords") or []),
                    }
                )
        return evidence

    # -------------------------------------------------------------------------
    @classmethod
    def _normalize_failure_category(
        cls, value: object
    ) -> (
        Literal[
            "model_capability",
            "provider_api",
            "schema_definition",
            "response_parsing",
            "context_limit",
        ]
        | None
    ):
        return (
            cast(
                Literal[
                    "model_capability",
                    "provider_api",
                    "schema_definition",
                    "response_parsing",
                    "context_limit",
                ],
                value,
            )
            if value in cls._FAILURE_CATEGORIES
            else None
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _overlay_commands(values: list[Any]) -> list[OverlayCommand]:
        """Convert model extraction into the typed mutation contract."""
        commands: list[OverlayCommand] = []
        for value in values:
            try:
                payload = (
                    value.model_dump(mode="json")
                    if hasattr(value, "model_dump")
                    else value
                )
                commands.append(OverlayCommand.model_validate(payload))
            except Exception:
                LOGGER.warning(
                    "Ignoring invalid overlay command from parser extraction"
                )
        return commands

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
        return any(
            self._contains_verbatim_span(user_message, term) for term in quoted_terms
        )

    # -------------------------------------------------------------------------
    def _extract_turn(
        self,
        *,
        user_message: str,
        memory_snapshot: dict[str, Any],
        recent_messages: list[dict[str, str]],
        active_instructions: list[dict[str, Any]] | None = None,
        task_snapshot: dict[str, Any] | None = None,
        schema_correction: bool = False,
    ) -> LLMParserExtraction:
        settings = None
        if self.provider is None or self.model is None:
            settings = self.settings_repo.get_required()
        if settings is None:
            provider_name = self.provider
            model_name = self.model
        else:
            provider_name = self.provider or settings.agent_model_provider
            model_name = self.model or settings.agent_model_name
        if provider_name is None or model_name is None:
            raise LLMConfigurationError(
                "Agent provider and model must be configured for structured extraction."
            )
        parser_provider = self.llm_factory.get_provider(provider_name)
        self.last_context_usage = None
        prompt_payload = {
            "user_message": user_message,
            "memory_snapshot": memory_snapshot,
            "recent_messages": recent_messages[-6:],
            "active_instructions": active_instructions or [],
            "task_snapshot": task_snapshot,
            "capability_catalog": self._catalog_evidence(),
        }
        parser_prompt = build_parser_prompt(schema_correction=schema_correction)
        request = LLMRequest(
            model=model_name,
            temperature=0.0,
            provider=provider_name,
            tools=[],
            tool_choice="none",
            messages=[
                {
                    "role": "system",
                    "content": parser_prompt,
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
        self.last_context_usage = dict(usage) if is_json_object(usage) else None
        try:
            extracted = LLMParserExtraction.model_validate(payload)
        except Exception as exc:  # noqa: BLE001
            raise LLMResponseParsingError(
                provider=provider_name,
                model=model_name,
                stage="structured_intent_extraction",
                detail="The provider response did not match the AEGIS extraction schema.",
            ) from exc
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
            extracted.viewport_intent.scope
            if extracted.viewport_intent is not None
            else None,
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
    @classmethod
    def build_parser_failure_turn_result(
        cls,
        *,
        user_message: str,
        memory_snapshot: dict[str, Any],
        conversation_messages: list[dict[str, Any]],
        provider_error: dict[str, Any],
    ) -> TurnParseResult:
        """Return a non-executable contract when structured extraction fails.

        A timeout or provider error is not evidence of user intent.  The
        contract therefore contains no inferred location, layer, basemap, or
        map action and can only be handled by the diagnostic path.
        """

        extracted = LLMParserExtraction(
            task_class="unclear",
            action_id=AgentAction.UNKNOWN.value,
            action_label="Structured extraction failed",
            task_tags=[],
            action_tags=[],
            requires_location=False,
            ambiguities=["parser_timeout"],
            parser_confidence=0.0,
            expected_frontend_update="failure_diagnostic",
        )
        normalized_recent = cls._normalize_recent_messages(conversation_messages)
        locations = [
            LocationSignal(
                signal_type=item.signal_type,
                raw_value=item.raw_value,
                normalized_value=item.normalized_value or item.raw_value,
                latitude=item.latitude,
                longitude=item.longitude,
                confidence=item.confidence,
                source="text",
            )
            for item in extracted.location_signals
            if item.raw_value.strip()
        ]
        ambiguities = cls._dedupe([*extracted.ambiguities, "parser_timeout"])
        return TurnParseResult(
            user_text=user_message,
            conversation_context=ConversationContextSnapshot(
                recent_messages=normalized_recent,
                memory_snapshot=memory_snapshot,
            ),
            task_class=extracted.task_class,
            location_signals=locations,
            normalized_action=NormalizedAction(
                action_id=cls._normalize_action_id(
                    extracted.action_id, extracted.parser_confidence
                ),
                action_label=extracted.action_label.strip() or "General map request",
                task_tags=list(extracted.task_tags),
                action_tags=list(extracted.action_tags),
                requested_visualizations=list(extracted.requested_visualizations),
                requires_location=extracted.requires_location,
            ),
            temporal_signal=TemporalSignal(
                mode=extracted.temporal_signal.mode,
                raw_text=extracted.temporal_signal.raw_text,
                reference_time_iso=extracted.temporal_signal.reference_time_iso,
                start_time_iso=extracted.temporal_signal.start_time_iso,
                end_time_iso=extracted.temporal_signal.end_time_iso,
                granularity=extracted.temporal_signal.granularity,
                aggregation=extracted.temporal_signal.aggregation,
            ),
            context_query=ContextQuery(kind=extracted.context_query.kind),
            ambiguities=ambiguities,
            parser_confidence=min(0.35, extracted.parser_confidence),
            relationship=extracted.relationship,
            map_target=extracted.map_target,
            entity_target=extracted.entity_target,
            requested_layers=cls._dedupe(extracted.requested_layers),
            overlay_commands=cls._overlay_commands(extracted.overlay_commands),
            poi_categories=list(dict.fromkeys(extracted.poi_categories)),
            requested_basemap=extracted.requested_basemap,
            requested_attributes=cls._dedupe(extracted.requested_attributes),
            required_data_sources=cls._dedupe(extracted.required_data_sources),
            required_tool_category=extracted.required_tool_category,
            tools_needed=extracted.tools_needed,
            direct_response_sufficient=extracted.direct_response_sufficient,
            requires_reparse=False,
            capability_limitations=cls._dedupe(extracted.capability_limitations),
            expected_frontend_update=extracted.expected_frontend_update,
            atomic_tasks=[
                item.model_dump(mode="json") for item in extracted.atomic_tasks
            ],
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
            provider_error=provider_error,
            failure_category=cls._normalize_failure_category(
                provider_error.get("category")
                if is_json_object(provider_error)
                else None
            ),
        )

    # -------------------------------------------------------------------------
    def parse_turn(
        self,
        user_message: str,
        memory_snapshot: dict[str, Any],
        conversation_messages: list[dict[str, Any]],
        active_instructions: list[dict[str, Any]] | None = None,
        task_snapshot: dict[str, Any] | None = None,
    ) -> TurnParseResult:
        normalized_recent = self._normalize_recent_messages(conversation_messages)
        parser_failure_ambiguity: str | None = None
        parser_provider_error: dict[str, object] | None = None
        parser_failure_category: str | None = None
        try:
            extracted = self._extract_turn_with_retry(
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
            if isinstance(exc, LLMStructuredOutputError):
                failure_ambiguity = exc.code
                parser_failure_category = exc.category
                parser_provider_error = {
                    "code": exc.code,
                    "category": exc.category,
                    "provider": exc.provider,
                    "model": exc.model,
                    "stage": exc.stage,
                    "http_status": exc.http_status,
                    "retryable": exc.retryable,
                    "detail": exc.detail,
                }
            elif isinstance(exc, LLMProviderRequestError):
                failure_ambiguity = exc.code
                parser_failure_category = exc.category
                parser_provider_error = {
                    "code": exc.code,
                    "category": exc.category,
                    "provider": exc.provider,
                    "model": exc.model,
                    "stage": exc.stage,
                    "http_status": exc.http_status,
                    "retryable": exc.retryable,
                }
            else:
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

        # A model/provider failure must remain a failure.  Prose inspection
        # here would turn an unverified request into an executable map plan.
        extracted = self._apply_domain_rules(user_message, extracted, memory_snapshot)

        if parser_failure_ambiguity is None and not extracted.location_signals:
            coordinate_signal = self._extract_coordinate_signal(user_message)
            if coordinate_signal is not None:
                extracted = extracted.model_copy(
                    update={"location_signals": [coordinate_signal]}
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
        normalized_action = NormalizedAction(
            action_id=self._normalize_action_id(
                extracted.action_id, extracted.parser_confidence
            ),
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
            start_time_iso=extracted.temporal_signal.start_time_iso,
            end_time_iso=extracted.temporal_signal.end_time_iso,
            granularity=extracted.temporal_signal.granularity,
            aggregation=extracted.temporal_signal.aggregation,
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
        confidence = extracted.parser_confidence
        if ambiguities:
            confidence -= 0.15

        result = TurnParseResult(
            user_text=user_message,
            conversation_context=ConversationContextSnapshot(
                recent_messages=normalized_recent,
                memory_snapshot=memory_snapshot,
            ),
            task_class=extracted.task_class,
            location_signals=location_signals,
            normalized_action=normalized_action,
            temporal_signal=temporal_signal,
            context_query=ContextQuery(kind=extracted.context_query.kind),
            ambiguities=ambiguities,
            disallowed_patterns=disallowed,
            parser_confidence=max(0.0, min(1.0, confidence)),
            relationship=extracted.relationship,
            map_target=extracted.map_target,
            entity_target=extracted.entity_target,
            requested_layers=self._dedupe(extracted.requested_layers),
            overlay_commands=self._overlay_commands(extracted.overlay_commands),
            poi_categories=list(dict.fromkeys(extracted.poi_categories)),
            requested_basemap=extracted.requested_basemap,
            requested_attributes=self._dedupe(extracted.requested_attributes),
            required_data_sources=self._dedupe(extracted.required_data_sources),
            required_tool_category=extracted.required_tool_category,
            tools_needed=extracted.tools_needed,
            direct_response_sufficient=extracted.direct_response_sufficient,
            requires_reparse=extracted.requires_reparse,
            capability_limitations=self._dedupe(extracted.capability_limitations),
            expected_frontend_update=extracted.expected_frontend_update,
            atomic_tasks=[
                item.model_dump(mode="json") for item in extracted.atomic_tasks
            ],
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
            provider_error=parser_provider_error,
            failure_category=self._normalize_failure_category(parser_failure_category),
        )
        LOGGER.info(
            "parser_normalized task=%s action=%s relationship=%s locations=%d basemap=%s layers=%d viewport_scope=%s tighten=%s ambiguities=%s",
            result.task_class,
            result.normalized_action.action_id,
            result.relationship,
            len(result.location_signals),
            result.requested_basemap,
            len(result.requested_layers),
            result.viewport_intent.scope
            if result.viewport_intent is not None
            else None,
            (
                result.viewport_intent.tighten_relative_to_active
                if result.viewport_intent is not None
                else None
            ),
            ",".join(result.ambiguities) if result.ambiguities else "-",
        )
        return result

    # -------------------------------------------------------------------------
    def _extract_turn_with_retry(self, **kwargs: Any) -> LLMParserExtraction:
        try:
            return self._extract_turn(**kwargs)
        except LLMResponseParsingError as exc:
            LOGGER.warning(
                "Retrying parser schema correction provider=%s model=%s code=%s",
                exc.provider,
                exc.model,
                exc.code,
            )
            return self._extract_turn(**kwargs, schema_correction=True)
        except LLMProviderRequestError as exc:
            if not exc.retryable:
                raise
            LOGGER.warning(
                "Retrying transient parser provider failure provider=%s model=%s code=%s",
                exc.provider,
                exc.model,
                exc.code,
            )
            return self._extract_turn(**kwargs)

    # -------------------------------------------------------------------------
    @classmethod
    def _apply_domain_rules(
        cls,
        user_message: str,
        extracted: LLMParserExtraction,
        memory_snapshot: dict[str, Any],
    ) -> LLMParserExtraction:
        """Normalize validated model output without interpreting user prose."""
        _ = user_message, memory_snapshot
        return extracted.model_copy(
            update={
                "task_tags": cls._dedupe(extracted.task_tags),
                "action_tags": cls._dedupe(extracted.action_tags),
                "requested_visualizations": cls._dedupe(
                    extracted.requested_visualizations
                ),
                "requested_layers": cls._dedupe(extracted.requested_layers),
                "requested_attributes": cls._dedupe(extracted.requested_attributes),
                "required_data_sources": cls._dedupe(extracted.required_data_sources),
                "capability_limitations": cls._dedupe(extracted.capability_limitations),
            }
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _normalize_action_id(action_id: str, confidence: float) -> str:
        if confidence < 0.25:
            return AgentAction.UNKNOWN.value
        try:
            return AgentAction(str(action_id).strip()).value
        except ValueError:
            return AgentAction.UNKNOWN.value
