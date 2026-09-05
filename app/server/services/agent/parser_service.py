from __future__ import annotations

from typing import Any

from server.common.typing import is_json_array, is_json_object, json_array, json_object

import json
import re
from dataclasses import dataclass
from contextvars import ContextVar
from time import monotonic
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
from server.services.llm.context_profile_resolver import ModelContextProfileResolver
from server.services.llm.request_deadline import REQUEST_DEADLINE_METADATA_KEY
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.runtime_registry import RuntimeRegistry
from server.services.agent.turn_support import AgentTurnSupport


###############################################################################
@dataclass(frozen=True)
class ParserRunResult:
    turn_contract: TurnParseResult
    context_usage: dict[str, object] | None
    model_calls: int = 0


###############################################################################
class ParserService:
    PARSER_TIMEOUT_SECONDS = 35.0
    RETRY_MIN_REMAINING_SECONDS = 1.0
    PARSER_MAX_OUTPUT_TOKENS = 2048
    MAX_HISTORY_MESSAGES = 4
    MAX_HISTORY_CONTENT_CHARS = 640
    MAX_CATALOG_IDENTITIES = 24
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
        context_profile_resolver: ModelContextProfileResolver | None = None,
    ) -> None:
        self.llm_factory = llm_factory
        self.settings_repo = settings_repo
        self.provider = provider
        self.model = model
        self.capability_registry = capability_registry
        self.runtime_registry = runtime_registry
        self.context_profile_resolver = context_profile_resolver
        self._last_context_usage: ContextVar[dict[str, object] | None] = ContextVar(
            "aegis_parser_context_usage", default=None
        )
        self._last_model_calls: ContextVar[int] = ContextVar(
            "aegis_parser_model_calls", default=0
        )
        self._extraction_override: ContextVar[LLMParserExtraction | None] = ContextVar(
            "aegis_parser_extraction_override", default=None
        )
        self._extraction_override_error: ContextVar[Exception | None] = ContextVar(
            "aegis_parser_extraction_override_error", default=None
        )

    # -------------------------------------------------------------------------
    @property
    def last_context_usage(self) -> dict[str, object] | None:
        return self._last_context_usage.get()

    # -------------------------------------------------------------------------
    @last_context_usage.setter
    def last_context_usage(self, value: dict[str, object] | None) -> None:
        self._last_context_usage.set(value)

    # -------------------------------------------------------------------------
    @property
    def last_model_calls(self) -> int:
        return self._last_model_calls.get()

    # -------------------------------------------------------------------------
    def _record_model_call(self) -> None:
        self._last_model_calls.set(self.last_model_calls + 1)

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
    @classmethod
    def _compact_history_content(cls, role: str, content: object) -> str:
        text = cls._to_text(content).strip()
        if len(text) <= cls.MAX_HISTORY_CONTENT_CHARS:
            return text
        if role == "assistant":
            try:
                payload = json.loads(text)
            except (TypeError, json.JSONDecodeError):
                payload = None
            if is_json_object(payload):
                operation = json_object(payload.get("operation"))
                map_session = json_object(payload.get("map_session"))
                resolved = json_object(map_session.get("resolved_location"))
                turn_contract = json_object(payload.get("turn_contract"))
                normalized_action = json_object(
                    turn_contract.get("normalized_action")
                )
                summary = {
                    "assistant_message": str(
                        payload.get("assistant_message") or ""
                    )[:240],
                    "task_class": turn_contract.get("task_class"),
                    "action_id": normalized_action.get("action_id"),
                    "operation": {
                        "kind": operation.get("kind"),
                        "status": operation.get("status"),
                    },
                    "location": {
                        key: resolved.get(key)
                        for key in (
                            "label",
                            "city",
                            "country",
                            "location_type",
                        )
                        if resolved.get(key) is not None
                    },
                }
                return json.dumps(summary, ensure_ascii=True, separators=(",", ":"))
        return text[: cls.MAX_HISTORY_CONTENT_CHARS]

    # -------------------------------------------------------------------------
    @classmethod
    def _compact_recent_messages(
        cls, messages: list[dict[str, str]], *, include_history: bool
    ) -> list[dict[str, str]]:
        if not include_history:
            return []
        compacted: list[dict[str, str]] = []
        for message in messages[-cls.MAX_HISTORY_MESSAGES :]:
            compacted.append(
                {
                    "id": str(message.get("id") or ""),
                    "conversation_id": str(message.get("conversation_id") or ""),
                    "turn_index": str(message.get("turn_index") or ""),
                    "role": str(message.get("role") or "unknown"),
                    "content": cls._compact_history_content(
                        str(message.get("role") or "unknown"),
                        message.get("content"),
                    ),
                    "created_at": str(message.get("created_at") or ""),
                }
            )
        return compacted

    # -------------------------------------------------------------------------
    @staticmethod
    def _context_is_required(user_message: str) -> bool:
        return bool(
            re.search(
                r"\b(?:now|again|there|here|nearby|same|that|this|previous|before|add|remove|hide|keep|continue|also|back|first|second|third|last|former|latter|them|it|compare|about)\b",
                str(user_message or ""),
                flags=re.IGNORECASE,
            )
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _compact_location(value: object) -> dict[str, Any] | None:
        location = json_object(value)
        if not location:
            return None
        keys = (
            "label",
            "latitude",
            "longitude",
            "country",
            "city",
            "address",
            "location_type",
            "location_class",
            "bbox",
            "confidence",
        )
        return {
            key: location.get(key)
            for key in keys
            if location.get(key) is not None
        }

    # -------------------------------------------------------------------------
    @classmethod
    def _compact_memory_snapshot(
        cls, snapshot: dict[str, Any], *, include_active_context: bool
    ) -> dict[str, Any]:
        active_location = cls._compact_location(snapshot.get("active_location"))
        compacted: dict[str, Any] = {}
        if include_active_context:
            compacted["location_slots"] = [
                item
                for raw in json_array(snapshot.get("location_slots"))
                if (item := cls._compact_location(raw)) is not None
            ][:4]
            if active_location is not None:
                compacted["active_location"] = active_location
            active_visualization = json_object(snapshot.get("active_visualization"))
            if active_visualization:
                overlays = json_object(active_visualization.get("overlay_collection"))
                instances = [
                    {
                        key: item.get(key)
                        for key in ("instance_id", "capability_id", "label", "visible")
                        if item.get(key) is not None
                    }
                    for raw in json_array(overlays.get("instances"))
                    if (item := json_object(raw))
                ][:24]
                compacted["active_visualization"] = {
                    key: active_visualization.get(key)
                    for key in (
                        "session_id",
                        "basemap_id",
                        "center",
                        "bounds",
                        "viewport",
                    )
                    if active_visualization.get(key) is not None
                }
                compacted["active_visualization"]["overlay_collection"] = {
                    "collection_id": overlays.get("collection_id"),
                    "revision": overlays.get("revision"),
                    "instances": instances,
                }
        return compacted

    # -------------------------------------------------------------------------
    @staticmethod
    def _compact_task_snapshot(
        snapshot: dict[str, Any] | None,
        *,
        include_details: bool = True,
    ) -> dict[str, Any] | None:
        if not is_json_object(snapshot):
            return None
        goal = json_object(snapshot.get("goal"))
        task_keys = (
            ("id", "description", "kind", "status", "depends_on")
            if include_details
            else ("id", "kind", "status")
        )
        tasks = [
            {
                key: (
                    str(item.get(key) or "")[:240]
                    if key in {"description"}
                    else item.get(key)
                )
                for key in task_keys
                if item.get(key) is not None
            }
            for raw in json_array(snapshot.get("tasks"))
            if (item := json_object(raw))
        ][:6]
        return {
            "active_task_id": snapshot.get("active_task_id"),
            "goal": {
                key: (
                    str(goal.get(key) or "")[:240]
                    if key == "text"
                    else goal.get(key)
                )
                for key in (("id", "text", "status") if include_details else ("id", "status"))
                if goal.get(key) is not None
            },
            "tasks": tasks,
            "assumptions": [
                str(item)[:240]
                for item in json_array(snapshot.get("assumptions"))
                if str(item).strip()
            ][:8],
            "unresolved_questions": [
                str(item)[:240]
                for item in json_array(snapshot.get("unresolved_questions"))
                if str(item).strip()
            ][:8],
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def _compact_catalog_evidence(
        evidence: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        compacted: list[dict[str, Any]] = []
        for item in evidence:
            compacted.append(
                {
                    "id": item.get("id"),
                    "label": str(item.get("label") or "")[:160],
                    "capability_kind": item.get("capability_kind"),
                    "rendering_mode": item.get("rendering_mode"),
                    "capabilities": list(item.get("capabilities") or [])[:8],
                    "keywords": [
                        str(value)[:80]
                        for value in list(item.get("keywords") or [])[:8]
                    ],
                    "supported_categories": [
                        str(value)[:80]
                        for value in list(item.get("supported_categories") or [])[:8]
                    ],
                }
            )
        return compacted

    # -------------------------------------------------------------------------
    @staticmethod
    def _compact_instructions(
        instructions: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        compacted: list[dict[str, Any]] = []
        for raw in list(instructions or [])[:8]:
            item = json_object(raw)
            if not item:
                continue
            compacted.append(
                {
                    key: (
                        str(item.get(key) or "")[:240]
                        if key in {"normalized_text", "original_user_text"}
                        else item.get(key)
                    )
                    for key in (
                        "directive_id",
                        "normalized_text",
                        "original_user_text",
                        "scope",
                        "status",
                    )
                    if item.get(key) is not None
                }
            )
        return compacted

    # -------------------------------------------------------------------------
    def _parser_prompt_payload(
        self,
        *,
        user_message: str,
        memory_snapshot: dict[str, Any],
        recent_messages: list[dict[str, str]],
        active_instructions: list[dict[str, Any]] | None,
        task_snapshot: dict[str, Any] | None,
    ) -> dict[str, Any]:
        include_active_context = self._context_is_required(user_message)
        return {
            "user_message": user_message,
            "memory_snapshot": self._compact_memory_snapshot(
                memory_snapshot,
                include_active_context=include_active_context,
            ),
            "recent_messages": self._compact_recent_messages(
                recent_messages,
                include_history=include_active_context,
            ),
            "active_instructions": self._compact_instructions(active_instructions),
            "task_snapshot": self._compact_task_snapshot(
                task_snapshot,
                include_details=include_active_context,
            ),
            "capability_catalog": self._compact_catalog_evidence(
                self._relevant_catalog_evidence(user_message)
            ),
            "context_policy": {
                "explicit_current_turn_overrides_history": True,
                "hierarchical_location_signals_are_complementary": True,
            },
        }

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
                        "supported_categories": [
                            str(item).strip()
                            for item in metadata.get("supported_categories", [])
                            if isinstance(item, str) and item.strip()
                        ],
                    }
                )
        return evidence

    # -------------------------------------------------------------------------
    def _relevant_catalog_evidence(self, user_message: str) -> list[dict[str, Any]]:
        """Return only bounded capability identities useful for this turn."""

        evidence = self._catalog_evidence()
        if len(evidence) <= self.MAX_CATALOG_IDENTITIES:
            return evidence
        terms = {
            token
            for token in re.findall(r"[a-z0-9_]+", user_message.casefold())
            if len(token) >= 3
        }

        def score(item: dict[str, Any]) -> tuple[int, int]:
            searchable = " ".join(
                [
                    str(item.get("id") or ""),
                    str(item.get("label") or ""),
                    str(item.get("capability_kind") or ""),
                    *(str(value) for value in item.get("capabilities", [])),
                    *(str(value) for value in item.get("keywords", [])),
                    *(str(value) for value in item.get("supported_categories", [])),
                ]
            ).casefold()
            matches = sum(1 for term in terms if term in searchable)
            return matches, -evidence.index(item)

        ranked = sorted(evidence, key=score, reverse=True)
        return ranked[: self.MAX_CATALOG_IDENTITIES]

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
    @classmethod
    def _overlay_commands(
        cls, extracted: LLMParserExtraction
    ) -> list[OverlayCommand]:
        """Convert extraction into a complete typed mutation contract.

        Some providers describe map mutations in their atomic task graph while
        omitting the dedicated overlay command field.  The task graph is still
        typed execution evidence, so recover that mutation here instead of
        inspecting the user's prose or guessing a provider capability.  A
        removal sourced from the active map is deliberately canonicalized to a
        current-view visible-overlay selector so persisted instance ids cannot
        make a bulk mutation stale.
        """
        commands: list[OverlayCommand] = []
        for value in extracted.overlay_commands:
            try:
                payload = (
                    value.model_dump(mode="json")
                    if hasattr(value, "model_dump")
                    else value
                )
                if not is_json_object(payload):
                    raise TypeError("Overlay command must be an object.")
                payload = dict(payload)
                for field_name in ("selector", "scope", "patch", "state_reference"):
                    if payload.get(field_name) is None:
                        payload[field_name] = {}
                commands.append(OverlayCommand.model_validate(payload))
            except Exception:
                LOGGER.warning(
                    "Ignoring invalid overlay command from parser extraction"
                )
        for task in extracted.atomic_tasks:
            command = cls._overlay_command_from_atomic_task(task)
            if command is None:
                continue
            task_payload = (
                task.model_dump(mode="json")
                if hasattr(task, "model_dump")
                else task
            )
            if cls._is_bulk_active_overlay_removal(command, task_payload):
                replacement = next(
                    (
                        index
                        for index, existing in enumerate(commands)
                        if existing.action == "remove"
                        and existing.scope.kind == "current_view"
                    ),
                    None,
                )
                if replacement is None:
                    replacement = next(
                        (
                            index
                            for index, existing in enumerate(commands)
                            if existing.action == "remove"
                        ),
                        None,
                    )
                if replacement is not None:
                    existing = commands[replacement]
                    command = existing.model_copy(
                        update={
                            "selector": {
                                "instance_ids": [],
                                "capability_ids": [],
                                "concepts": [],
                                "labels": [],
                                "providers": [],
                                "overlay_types": [],
                                "rendering_modes": [],
                                "tags": [],
                                "visibility": "visible",
                            },
                            "scope": {
                                "kind": "current_view",
                                "location": None,
                                "label": None,
                            },
                        }
                    )
                    commands[replacement] = command
                    continue
            if command.model_dump(mode="json") not in [
                item.model_dump(mode="json") for item in commands
            ]:
                commands.append(command)
        return commands

    # -------------------------------------------------------------------------
    @classmethod
    def _overlay_command_from_atomic_task(cls, task: Any) -> OverlayCommand | None:
        payload = task.model_dump(mode="json") if hasattr(task, "model_dump") else task
        if not is_json_object(payload):
            return None
        changes = payload.get("visualization_changes")
        if not is_json_object(changes):
            return None
        action = changes.get("action")
        if action not in {"add", "remove", "keep_only", "show", "hide", "update"}:
            return None
        selector: dict[str, Any] = dict(json_object(changes.get("selector")))
        for field_name in (
            "instance_ids",
            "capability_ids",
            "concepts",
            "labels",
            "providers",
            "overlay_types",
            "rendering_modes",
            "tags",
            "visibility",
        ):
            if field_name in changes and field_name not in selector:
                selector[field_name] = changes[field_name]
        scope: dict[str, Any] = dict(json_object(changes.get("scope")))
        patch: dict[str, Any] = dict(json_object(changes.get("patch")))
        state_reference: dict[str, Any] = dict(
            json_object(changes.get("state_reference"))
        )
        if action == "remove" and cls._has_active_overlay_output(payload):
            selector = {"visibility": "visible"}
            scope = {"kind": "current_view"}
        try:
            return OverlayCommand.model_validate(
                {
                    "action": action,
                    "selector": selector,
                    "scope": scope,
                    "patch": patch,
                    "state_reference": state_reference,
                }
            )
        except Exception:
            return None

    # -------------------------------------------------------------------------
    @staticmethod
    def _is_bulk_active_overlay_removal(
        command: OverlayCommand, task_payload: object
    ) -> bool:
        return command.action == "remove" and ParserService._has_active_overlay_output(
            task_payload
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _has_active_overlay_output(task_payload: object) -> bool:
        if not is_json_object(task_payload):
            return False
        input_refs = {
            str(item).strip()
            for item in json_array(task_payload.get("input_refs"))
            if str(item).strip()
        }
        output_refs = {
            str(item).strip()
            for item in json_array(task_payload.get("output_refs"))
            if str(item).strip()
        }
        return "active_map_session" in input_refs and "overlay_removed" in output_refs

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
    def _build_extraction_request(
        self,
        *,
        user_message: str,
        memory_snapshot: dict[str, Any],
        recent_messages: list[dict[str, str]],
        active_instructions: list[dict[str, Any]] | None,
        task_snapshot: dict[str, Any] | None,
        schema_correction: bool,
        deadline_monotonic: float | None,
    ) -> tuple[str, str, Any, LLMRequest]:
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
        if deadline_monotonic is not None and monotonic() >= deadline_monotonic:
            raise LLMProviderRequestError(
                provider=provider_name,
                model=model_name,
                stage="structured_intent_extraction",
                code="provider_timeout",
                retryable=False,
                timeout_origin="application_deadline",
            )
        prompt_payload = self._parser_prompt_payload(
            user_message=user_message,
            memory_snapshot=memory_snapshot,
            recent_messages=recent_messages,
            active_instructions=active_instructions,
            task_snapshot=task_snapshot,
        )
        request = LLMRequest(
            model=model_name,
            temperature=0.0,
            provider=provider_name,
            tools=[],
            tool_choice="none",
            metadata={
                **(
                    self.context_profile_resolver.request_metadata(
                        provider_name,
                        model_name,
                    )
                    if self.context_profile_resolver is not None
                    else {}
                ),
                "max_tokens": self.PARSER_MAX_OUTPUT_TOKENS,
                "purpose": "structured_intent_extraction",
                **(
                    {REQUEST_DEADLINE_METADATA_KEY: deadline_monotonic}
                    if deadline_monotonic is not None
                    else {}
                ),
            },
            messages=[
                {
                    "role": "system",
                    "content": build_parser_prompt(schema_correction=schema_correction),
                },
                {
                    "role": "user",
                    "content": json.dumps(prompt_payload, ensure_ascii=True),
                },
            ],
        )
        return (
            provider_name,
            model_name,
            self.llm_factory.get_provider(provider_name),
            request,
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
        deadline_monotonic: float | None = None,
    ) -> LLMParserExtraction:
        provider_name, model_name, parser_provider, request = (
            self._build_extraction_request(
                user_message=user_message,
                memory_snapshot=memory_snapshot,
                recent_messages=recent_messages,
                active_instructions=active_instructions,
                task_snapshot=task_snapshot,
                schema_correction=schema_correction,
                deadline_monotonic=deadline_monotonic,
            )
        )
        self.last_context_usage = None
        self._record_model_call()
        payload = parser_provider.structured_output(
            request=request, schema=LLMParserExtraction
        )
        usage = getattr(payload, "context_usage", None)
        self.last_context_usage = dict(usage) if is_json_object(usage) else None
        try:
            extracted = LLMParserExtraction.model_validate(payload)
        except Exception as exc:  # noqa: BLE001
            raise LLMResponseParsingError(
                provider=provider_name,
                model=model_name,
                stage="structured_intent_extraction",
                detail="The provider response did not match the AEGIS extraction schema.",
                context_usage=(
                    dict(self.last_context_usage)
                    if is_json_object(self.last_context_usage)
                    else None
                ),
            ) from exc
        LOGGER.debug(
            "Parser LLM extraction: provider=%s model=%s task=%s action=%s",
            provider_name,
            model_name,
            extracted.task_class,
            extracted.action_id,
        )
        LOGGER.debug(
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
    async def _extract_turn_async(
        self,
        *,
        user_message: str,
        memory_snapshot: dict[str, Any],
        recent_messages: list[dict[str, str]],
        active_instructions: list[dict[str, Any]] | None = None,
        task_snapshot: dict[str, Any] | None = None,
        schema_correction: bool = False,
        deadline_monotonic: float | None = None,
    ) -> LLMParserExtraction:
        provider_name, model_name, parser_provider, request = (
            self._build_extraction_request(
                user_message=user_message,
                memory_snapshot=memory_snapshot,
                recent_messages=recent_messages,
                active_instructions=active_instructions,
                task_snapshot=task_snapshot,
                schema_correction=schema_correction,
                deadline_monotonic=deadline_monotonic,
            )
        )
        self.last_context_usage = None
        self._record_model_call()
        payload = await parser_provider.astructured_output(
            request=request, schema=LLMParserExtraction
        )
        usage = getattr(payload, "context_usage", None)
        self.last_context_usage = dict(usage) if is_json_object(usage) else None
        try:
            extracted = LLMParserExtraction.model_validate(payload)
        except Exception as exc:  # noqa: BLE001
            raise LLMResponseParsingError(
                provider=provider_name,
                model=model_name,
                stage="structured_intent_extraction",
                detail="The provider response did not match the AEGIS extraction schema.",
                context_usage=(
                    dict(self.last_context_usage)
                    if is_json_object(self.last_context_usage)
                    else None
                ),
            ) from exc
        LOGGER.debug(
            "Parser async extraction: provider=%s model=%s task=%s action=%s",
            provider_name,
            model_name,
            extracted.task_class,
            extracted.action_id,
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
    def _extract_deictic_reference(user_message: str) -> str | None:
        """Extract a location-reference phrase the model may omit.

        Deictic references are a language boundary concern, not a place-name
        or provider heuristic.  The structured parser is still authoritative
        for intent; this small deterministic supplement makes the memory
        resolver reliable when a valid model response leaves out ``there`` or
        an equivalent reference.
        """
        message = str(user_message or "")
        for pattern in (
            r"\baround\s+(?:here|there)\b",
            r"\bnear\s+me\b",
            r"\bmy\s+location\b",
            r"\bwhere\s+(?:i|we)\s+am\b",
            r"\b(?:this|that|the\s+same)\s+(?:area|place|location)\b",
            r"\bnearby\b",
            r"\bhere\b",
        ):
            match = re.search(pattern, message, flags=re.IGNORECASE)
            if match is not None:
                return match.group(0)

        # Avoid treating existential constructions such as "there are
        # hospitals" as a reference to the active conversation location.
        if re.search(
            r"\bthere\s+(?:is|are|was|were|has|have|will|would|can|could)\b",
            message,
            flags=re.IGNORECASE,
        ):
            return None
        match = re.search(r"\bthere\b", message, flags=re.IGNORECASE)
        return match.group(0) if match is not None else None

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
            ambiguities=[
                str(provider_error.get("code") or "provider_timeout")
            ],
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
        ambiguities = cls._dedupe(
            [
                *extracted.ambiguities,
                str(provider_error.get("code") or "provider_timeout"),
            ]
        )
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
                requested_concepts=cls._dedupe(extracted.requested_concepts),
                requested_layers=cls._dedupe(extracted.requested_layers),
            overlay_commands=cls._overlay_commands(extracted),
                poi_categories=list(dict.fromkeys(extracted.poi_categories)),
                radius_m=extracted.radius_m,
                result_limit=extracted.result_limit,
                presentation_mode=extracted.presentation_mode,
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
            failure_category=(
                cls._normalize_failure_category(
                    provider_error.get("category")
                    if is_json_object(provider_error)
                    else None
                )
                or "provider_api"
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
        deadline_monotonic: float | None = None,
    ) -> TurnParseResult:
        return self.parse_turn_with_usage(
            user_message=user_message,
            memory_snapshot=memory_snapshot,
            conversation_messages=conversation_messages,
            active_instructions=active_instructions,
            task_snapshot=task_snapshot,
            deadline_monotonic=deadline_monotonic,
        ).turn_contract

    # -------------------------------------------------------------------------
    def parse_turn_with_usage(
        self,
        user_message: str,
        memory_snapshot: dict[str, Any],
        conversation_messages: list[dict[str, Any]],
        active_instructions: list[dict[str, Any]] | None = None,
        task_snapshot: dict[str, Any] | None = None,
        deadline_monotonic: float | None = None,
    ) -> ParserRunResult:
        self.last_context_usage = None
        self._last_model_calls.set(0)
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
                deadline_monotonic=deadline_monotonic,
            )
        except LLMConfigurationError:
            raise
        except Exception as exc:
            LOGGER.warning(
                "Parser LLM extraction failed category=%s code=%s provider=%s model=%s",
                getattr(exc, "category", None) or "provider_api",
                getattr(exc, "code", None) or type(exc).__name__,
                getattr(exc, "provider", None) or self.provider or "unknown",
                getattr(exc, "model", None) or self.model or "unknown",
            )
            failure_context_usage = getattr(exc, "context_usage", None)
            if is_json_object(failure_context_usage):
                self.last_context_usage = dict(failure_context_usage)
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
                    "detail": str(exc),
                    "timeout_origin": exc.timeout_origin,
                    "elapsed_ms": exc.elapsed_ms,
                }
            else:
                failure_ambiguity = (
                    "parser_authentication_failed"
                    if "invalid_api_key" in str(exc).lower() or "401" in str(exc)
                    else "parser_unavailable"
                )
                parser_failure_category = "provider_api"
                parser_provider_error = {
                    "code": failure_ambiguity,
                    "category": "provider_api",
                    "provider": self.provider or "",
                    "model": self.model or "",
                    "stage": "structured_intent_extraction",
                    "retryable": False,
                    "detail": str(exc),
                }
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
        extracted = self._apply_domain_rules(
            user_message,
            extracted,
            memory_snapshot,
            capability_catalog=(
                self._catalog_evidence()
                if parser_failure_ambiguity is None
                else None
            ),
        )
        if (
            extracted.context_query.kind != "none"
            and AgentTurnSupport.has_executable_intent(extracted)
        ):
            LOGGER.debug(
                "parser_context_query_suppressed action=%s task=%s context_query=%s",
                extracted.action_id,
                extracted.task_class,
                extracted.context_query.kind,
            )
            extracted = extracted.model_copy(
                update={
                    "context_query": extracted.context_query.model_copy(
                        update={"kind": "none"}
                    )
                }
            )

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
        if parser_failure_ambiguity is None and not location_signals:
            deictic_reference = self._extract_deictic_reference(user_message)
            if deictic_reference is not None:
                location_signals.append(
                    LocationSignal(
                        signal_type="deictic",
                        raw_value=deictic_reference,
                        normalized_value=deictic_reference,
                        confidence=0.95,
                        source="text",
                    )
                )
        normalized_action = NormalizedAction(
            action_id=self._normalize_action_id(
                extracted.action_id,
                extracted.parser_confidence,
                task_class=extracted.task_class,
                requested_concepts=extracted.requested_concepts,
                requested_layers=extracted.requested_layers,
                action_tags=extracted.action_tags,
                required_tool_category=extracted.required_tool_category,
                entity_target=extracted.entity_target,
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
            LOGGER.debug(
                "Parser missing location: action=%s ambiguities=%s",
                normalized_action.action_id,
                ambiguities,
            )
        confidence = extracted.parser_confidence
        if ambiguities:
            confidence -= 0.15

        result = TurnParseResult(
            user_text=user_message,
            conversation_context=ConversationContextSnapshot(
                recent_messages=self._compact_recent_messages(
                    normalized_recent,
                    include_history=True,
                ),
                memory_snapshot=self._compact_memory_snapshot(
                    memory_snapshot,
                    include_active_context=True,
                ),
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
            requested_concepts=self._dedupe(extracted.requested_concepts),
            requested_layers=self._dedupe(extracted.requested_layers),
            overlay_commands=self._overlay_commands(extracted),
            poi_categories=list(dict.fromkeys(extracted.poi_categories)),
            radius_m=extracted.radius_m,
            result_limit=extracted.result_limit,
            presentation_mode=extracted.presentation_mode,
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
        LOGGER.debug(
            "parser_normalized task=%s action=%s relationship=%s context_query=%s tools_needed=%s direct_response_sufficient=%s locations=%d basemap=%s layers=%d concepts=%s viewport_scope=%s tighten=%s ambiguities=%s",
            result.task_class,
            result.normalized_action.action_id,
            result.relationship,
            result.context_query.kind,
            result.tools_needed,
            result.direct_response_sufficient,
            len(result.location_signals),
            result.requested_basemap,
            len(result.requested_layers),
            ",".join(result.requested_concepts) if result.requested_concepts else "-",
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
        return ParserRunResult(
            turn_contract=result,
            context_usage=(
                dict(self.last_context_usage)
                if is_json_object(self.last_context_usage)
                else None
            ),
            model_calls=self.last_model_calls,
        )

    # -------------------------------------------------------------------------
    def _extract_turn_with_retry(self, **kwargs: Any) -> LLMParserExtraction:
        override_error = self._extraction_override_error.get()
        if override_error is not None:
            raise override_error
        override = self._extraction_override.get()
        if override is not None:
            return override
        deadline = kwargs.get("deadline_monotonic")

        def retry_allowed() -> bool:
            if not isinstance(deadline, (int, float)):
                return True
            return monotonic() + self.RETRY_MIN_REMAINING_SECONDS < float(deadline)

        try:
            return self._extract_turn(**kwargs)
        except LLMResponseParsingError as exc:
            if not retry_allowed():
                raise
            LOGGER.warning(
                "Retrying parser schema correction provider=%s model=%s code=%s",
                exc.provider,
                exc.model,
                exc.code,
            )
            return self._extract_turn(**kwargs, schema_correction=True)
        except LLMProviderRequestError as exc:
            if not exc.retryable or not retry_allowed():
                raise
            LOGGER.warning(
                "Retrying transient parser provider failure provider=%s model=%s code=%s",
                exc.provider,
                exc.model,
                exc.code,
            )
            return self._extract_turn(**kwargs)

    # -------------------------------------------------------------------------
    async def parse_turn_with_usage_async(
        self,
        user_message: str,
        memory_snapshot: dict[str, Any],
        conversation_messages: list[dict[str, Any]],
        active_instructions: list[dict[str, Any]] | None = None,
        task_snapshot: dict[str, Any] | None = None,
        deadline_monotonic: float | None = None,
    ) -> ParserRunResult:
        """Parse a turn without running the blocking provider on the event loop."""

        extracted: LLMParserExtraction | None = None
        provider_error: Exception | None = None
        usage: dict[str, object] | None = None
        model_calls = 0
        try:
            self._last_model_calls.set(0)
            extracted = await self._extract_turn_with_retry_async(
                user_message=user_message,
                memory_snapshot=memory_snapshot,
                recent_messages=self._normalize_recent_messages(conversation_messages),
                active_instructions=active_instructions,
                task_snapshot=task_snapshot,
                deadline_monotonic=deadline_monotonic,
            )
            current_usage = self.last_context_usage
            usage = dict(current_usage) if is_json_object(current_usage) else None
        except LLMConfigurationError:
            raise
        except Exception as exc:
            provider_error = exc
        model_calls = self.last_model_calls

        extraction_token = self._extraction_override.set(extracted)
        error_token = self._extraction_override_error.set(provider_error)
        try:
            result = self.parse_turn_with_usage(
                user_message=user_message,
                memory_snapshot=memory_snapshot,
                conversation_messages=conversation_messages,
                active_instructions=active_instructions,
                task_snapshot=task_snapshot,
                deadline_monotonic=deadline_monotonic,
            )
        finally:
            self._extraction_override.reset(extraction_token)
            self._extraction_override_error.reset(error_token)
        if usage is not None:
            self.last_context_usage = usage
            result = ParserRunResult(
                turn_contract=result.turn_contract,
                context_usage=usage,
                model_calls=model_calls,
            )
        else:
            result = ParserRunResult(
                turn_contract=result.turn_contract,
                context_usage=result.context_usage,
                model_calls=model_calls,
            )
        return result

    # -------------------------------------------------------------------------
    async def _extract_turn_with_retry_async(
        self, **kwargs: Any
    ) -> LLMParserExtraction:
        deadline = kwargs.get("deadline_monotonic")

        def retry_allowed() -> bool:
            if not isinstance(deadline, (int, float)):
                return True
            return monotonic() + self.RETRY_MIN_REMAINING_SECONDS < float(deadline)

        try:
            return await self._extract_turn_async(**kwargs)
        except LLMResponseParsingError as exc:
            if not retry_allowed():
                raise
            LOGGER.warning(
                "Retrying async parser schema correction provider=%s model=%s code=%s",
                exc.provider,
                exc.model,
                exc.code,
            )
            return await self._extract_turn_async(**kwargs, schema_correction=True)
        except LLMProviderRequestError as exc:
            if not exc.retryable or not retry_allowed():
                raise
            LOGGER.warning(
                "Retrying transient async parser provider failure provider=%s model=%s code=%s",
                exc.provider,
                exc.model,
                exc.code,
            )
            return await self._extract_turn_async(**kwargs)

    # -------------------------------------------------------------------------
    @classmethod
    def _apply_domain_rules(
        cls,
        user_message: str,
        extracted: LLMParserExtraction,
        memory_snapshot: dict[str, Any],
        capability_catalog: list[dict[str, Any]] | None = None,
    ) -> LLMParserExtraction:
        """Normalize validated model output without interpreting user prose."""
        _ = user_message, memory_snapshot
        poi_categories = cls._recover_catalog_poi_categories(
            user_message,
            extracted,
            capability_catalog,
        )
        execution_required = cls._has_typed_execution_evidence(extracted)
        normalized_action_id = extracted.action_id
        if (
            execution_required
            and extracted.task_class == "map_search"
            and extracted.location_signals
            and normalized_action_id == AgentAction.UNKNOWN.value
        ):
            normalized_action_id = AgentAction.LOCATION_RENDER.value
        requires_location = extracted.requires_location or (
            extracted.task_class == "map_search"
            or (
                extracted.task_class == "direct_query"
                and bool(extracted.location_signals)
            )
        )
        return extracted.model_copy(
            update={
                "action_id": normalized_action_id,
                "tools_needed": extracted.tools_needed or execution_required,
                "direct_response_sufficient": (
                    extracted.direct_response_sufficient
                    and not execution_required
                ),
                "requires_location": requires_location,
                "task_tags": cls._dedupe(extracted.task_tags),
                "action_tags": cls._dedupe(extracted.action_tags),
                "requested_visualizations": cls._dedupe(
                    extracted.requested_visualizations
                ),
                "requested_concepts": cls._dedupe(extracted.requested_concepts),
                "requested_layers": cls._dedupe(extracted.requested_layers),
                "requested_attributes": cls._dedupe(extracted.requested_attributes),
                "poi_categories": cls._dedupe(
                    [*extracted.poi_categories, *poi_categories]
                ),
                "required_data_sources": cls._dedupe(extracted.required_data_sources),
                "capability_limitations": cls._dedupe(extracted.capability_limitations),
            }
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _has_typed_execution_evidence(extracted: LLMParserExtraction) -> bool:
        """Derive execution from typed intent instead of a model boolean."""

        if extracted.task_class not in {"map_search", "direct_query"}:
            return False
        if extracted.task_class == "map_search":
            return True
        if extracted.action_id in {
            AgentAction.CHAT_RESPONSE.value,
            AgentAction.UNKNOWN.value,
        }:
            return any(
                (
                    extracted.location_signals,
                    extracted.requested_concepts,
                    extracted.requested_layers,
                    extracted.requested_visualizations,
                    extracted.requested_basemap,
                    extracted.required_data_sources,
                    extracted.required_tool_category,
                    extracted.poi_categories,
                    extracted.atomic_tasks,
                    extracted.overlay_commands,
                    extracted.viewport_intent,
                )
            )
        return True

    # -------------------------------------------------------------------------
    @classmethod
    def _recover_catalog_poi_categories(
        cls,
        user_message: str,
        extracted: LLMParserExtraction,
        capability_catalog: list[dict[str, Any]] | None,
    ) -> list[str]:
        """Recover explicit POI categories omitted by a valid model response.

        This is deliberately catalog-backed and intent-gated.  It does not
        infer a layer or a provider from arbitrary prose; it only restores a
        category value when the parser already identified a POI retrieval
        request and an enabled capability declares that category.
        """
        if not capability_catalog or extracted.poi_categories:
            return []
        if extracted.task_class != "map_search":
            return []
        intent_text = " ".join(
            [
                extracted.action_id,
                *extracted.task_tags,
                *extracted.action_tags,
                *extracted.requested_visualizations,
                *extracted.requested_concepts,
            ]
        )
        if not re.search(
            r"\b(?:poi|amenit(?:y|ies)|nearby\s+places?|place\s+discovery|service\s+discovery)\b",
            cls._normalize_category_text(intent_text),
        ):
            return []
        normalized_message = cls._normalize_category_text(user_message)
        recovered: list[str] = []
        for capability in capability_catalog:
            categories = capability.get("supported_categories")
            if not is_json_array(categories):
                continue
            for category in categories:
                if not isinstance(category, str) or not category.strip():
                    continue
                normalized_category = cls._normalize_category_text(category)
                if re.search(
                    rf"(?<!\w){re.escape(normalized_category)}(?!\w)",
                    normalized_message,
                ):
                    recovered.append(category.strip())
        return cls._dedupe(recovered)

    # -------------------------------------------------------------------------
    @staticmethod
    def _normalize_category_text(value: object) -> str:
        return re.sub(
            r"\s+",
            " ",
            re.sub(r"[^\w]+", " ", str(value or "").casefold()),
        ).strip()

    # -------------------------------------------------------------------------
    @staticmethod
    def _normalize_action_id(
        action_id: str,
        confidence: float,
        *,
        task_class: str = "unclear",
        requested_concepts: list[str] | None = None,
        requested_layers: list[str] | None = None,
        action_tags: list[str] | None = None,
        required_tool_category: str | None = None,
        entity_target: str | None = None,
    ) -> str:
        if confidence < 0.25:
            return AgentAction.UNKNOWN.value
        try:
            return AgentAction(str(action_id).strip()).value
        except ValueError:
            # Model action labels are not executable identities. When a model
            # emits an unregistered label but the typed task still contains a
            # concrete data request, retain the generic executable action and
            # let capability resolution select the actual catalog item.
            semantic_evidence = [
                *(requested_concepts or []),
                *(requested_layers or []),
                *(action_tags or []),
                required_tool_category or "",
                entity_target or "",
            ]
            if task_class in {"map_search", "direct_query"} and any(
                str(value).strip() for value in semantic_evidence
            ):
                return AgentAction.GEOSPATIAL_DATA_RETRIEVAL.value
            return AgentAction.UNKNOWN.value
