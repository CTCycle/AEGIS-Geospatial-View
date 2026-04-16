from __future__ import annotations

import logging
import os
import re
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from AEGIS.server.configurations import get_server_settings
from AEGIS.server.domain.agent.task_scope import TaskScopeDecision
from AEGIS.server.domain.chat import ChatTurnRequest, ChatTurnResponse
from AEGIS.server.domain.extraction.models import ExtractedIntent, ExtractedIntentPatch, StageAParserIntent, StageBSearchExtraction
from AEGIS.server.domain.extraction.patching import merge_extracted_intent
from AEGIS.server.domain.geographics import LocationSearchRequest
from AEGIS.server.repositories.chat_history import ChatHistoryRepository
from AEGIS.server.repositories.model_settings import ModelSettingsRepository
from AEGIS.server.repositories.session_catalog import SessionCatalogRepository
from AEGIS.server.repositories.session_details import SessionDetailsRepository
from AEGIS.server.services.agent.chat_response_service import ChatResponseService
from AEGIS.server.services.agent.decision_service import DecisionService
from AEGIS.server.services.agent.parser_service import ParserService
from AEGIS.server.services.agent.task_scope_service import TaskScopeService
from AEGIS.server.services.agent.tools import AgentTools
from AEGIS.server.services.chat.history_buffer import ChatHistoryBuffer
from AEGIS.server.services.geospatial.manifest_loader import GeospatialManifestLoader
from AEGIS.server.services.llm.factory import LLMFactory
from AEGIS.server.services.llm.context_builder import build_conversation_context
from AEGIS.server.services.llm.ollama import OllamaProvider
from AEGIS.server.services.search.intent_mapper import map_structured_intent_to_location_request
from AEGIS.server.services.search.orchestrator import LocationSearchOrchestrator
from AEGIS.server.services.vector.retriever import VectorRetriever

logger = logging.getLogger(__name__)

###############################################################################
class AgentOrchestrator:
    SAME_LOCATION_PATTERNS = (
        re.compile(r"\b(same place|same area|as before|there|that place|same location)\b", re.IGNORECASE),
    )
    COORDINATE_RE = re.compile(r"[+-]?\d{1,2}(?:\.\d+)?\s*[, ]\s*[+-]?\d{1,3}(?:\.\d+)?")
    OVERLAY_KEYWORD_TO_IDS: dict[str, tuple[str, ...]] = {
        "traffic": ("tomtom_traffic_flow",),
        "air quality": ("openmeteo_air_quality_forecast", "openaq_air_quality"),
        "pm2.5": ("openmeteo_air_quality_forecast", "openaq_air_quality"),
        "weather": ("openmeteo_weather_forecast", "rainviewer_precipitation_radar"),
        "radar": ("rainviewer_precipitation_radar",),
        "rain": ("rainviewer_precipitation_radar",),
        "poi": ("overpass_poi_amenities",),
        "amenit": ("overpass_poi_amenities",),
        "solar": ("pvgis_solar",),
    }

    def __init__(
        self,
        *,
        search_orchestrator: LocationSearchOrchestrator,
        history_repo: ChatHistoryRepository | None = None,
        history_buffer: ChatHistoryBuffer | None = None,
        settings_repo: ModelSettingsRepository | None = None,
        llm_factory: LLMFactory | None = None,
        vector_retriever: VectorRetriever | None = None,
        manifest_loader: GeospatialManifestLoader | None = None,
        session_catalog_repo: SessionCatalogRepository | None = None,
        session_details_repo: SessionDetailsRepository | None = None,
        agent_tools: AgentTools | None = None,
        task_scope_service: TaskScopeService | None = None,
    ) -> None:
        self.search_orchestrator = search_orchestrator
        self.history_repo = history_repo or ChatHistoryRepository()
        self.history_buffer = history_buffer or ChatHistoryBuffer(history_repo=self.history_repo)
        self.settings_repo = settings_repo or ModelSettingsRepository()
        self.llm_factory = llm_factory or LLMFactory()
        self.vector_retriever = vector_retriever or VectorRetriever()
        self.manifest_loader = manifest_loader or GeospatialManifestLoader()
        self.session_catalog_repo = session_catalog_repo or SessionCatalogRepository()
        self.session_details_repo = session_details_repo or SessionDetailsRepository()
        self.agent_tools = agent_tools
        self.task_scope_service = task_scope_service or TaskScopeService()
        nominatim_service = getattr(self.search_orchestrator, "nominatim_service", None)
        self.catalog_service = getattr(self.search_orchestrator, "catalog_service", None)
        catalog_service = self.catalog_service
        if self.agent_tools is None and nominatim_service is not None and catalog_service is not None:
            self.agent_tools = AgentTools(
                nominatim_service=nominatim_service,
                catalog_service=catalog_service,
                search_orchestrator=self.search_orchestrator,
            )
        self._debug_logs_enabled = str(os.getenv("AEGIS_AGENT_DEBUG", "")).strip().lower() in {"1", "true", "yes", "on"}

    def _debug_log(self, event: str, payload: dict[str, Any]) -> None:
        if not self._debug_logs_enabled:
            return
        logger.info("agent_debug %s %s", event, payload)

    def _references_prior_location(self, user_message: str) -> bool:
        return any(pattern.search(user_message) for pattern in self.SAME_LOCATION_PATTERNS)

    def _message_has_coordinates(self, user_message: str) -> bool:
        return bool(self.COORDINATE_RE.search(user_message))

    def _looks_like_location_phrase(self, user_message: str) -> bool:
        normalized = user_message.strip()
        if len(normalized) < 3:
            return False
        if re.search(r"\b(?:near|nearby|around|at|in|via|street|road|avenue|square|piazza)\b", normalized, re.IGNORECASE):
            return True
        if re.search(r"\d{1,5}\s+[a-zA-Z]", normalized):
            return True
        return "," in normalized

    def _normalize_extracted_state_for_turn(
        self,
        *,
        extracted_state: ExtractedIntent,
        user_message: str,
    ) -> ExtractedIntent:
        references_prior = self._references_prior_location(user_message)
        has_message_coordinates = self._message_has_coordinates(user_message)
        has_text_location = any(
            [
                extracted_state.location.address,
                extracted_state.location.city,
                extracted_state.location.country,
            ]
        )
        has_coordinates = (
            extracted_state.coordinates.latitude is not None
            and extracted_state.coordinates.longitude is not None
        )
        if references_prior:
            return extracted_state
        if has_message_coordinates and has_coordinates:
            return extracted_state.model_copy(
                update={
                    "location": extracted_state.location.model_copy(
                        update={
                            "address": None,
                            "city": None,
                            "country": None,
                        }
                    )
                }
            )
        if has_text_location and not has_message_coordinates and self._looks_like_location_phrase(user_message):
            return extracted_state.model_copy(
                update={
                    "coordinates": extracted_state.coordinates.model_copy(
                        update={"latitude": None, "longitude": None}
                    )
                }
            )
        if (
            has_coordinates
            and not has_text_location
            and not has_message_coordinates
            and self._looks_like_location_phrase(user_message)
        ):
            return extracted_state.model_copy(
                update={
                    "coordinates": extracted_state.coordinates.model_copy(
                        update={"latitude": None, "longitude": None}
                    )
                }
            )
        return extracted_state

    def _derive_location_query_from_message(self, user_message: str) -> str | None:
        normalized = user_message.strip()
        if not normalized:
            return None
        around_match = re.search(r"\b(?:near|around|in|at)\s+([a-z0-9][a-z0-9\s,'\-]{2,})$", normalized, re.IGNORECASE)
        if around_match:
            return around_match.group(1).strip(" .")
        stripped = re.sub(
            r"^(?:please\s+)?(?:find|show|check|locate|center|map|i need to check|i need to find)\s+",
            "",
            normalized,
            flags=re.IGNORECASE,
        )
        stripped = re.sub(r"\b(?:and show|with)\b.*$", "", stripped, flags=re.IGNORECASE).strip()
        return stripped or normalized

    def _fallback_overlay_ids_from_retrieval(
        self,
        *,
        user_message: str,
        stage_b: StageBSearchExtraction,
        retrieval: dict[str, list[dict[str, object]]],
    ) -> list[str]:
        normalized = f"{user_message} {' '.join(stage_b.required_overlays)}".lower()
        requested: list[str] = []
        for keyword, overlay_ids in self.OVERLAY_KEYWORD_TO_IDS.items():
            if keyword in normalized:
                requested.extend(overlay_ids)
        if not requested:
            return []
        available_ids = {
            str(item.get("id"))
            for item in retrieval.get("overlays", [])
            if isinstance(item, dict) and bool(item.get("is_available", True))
        }
        selected: list[str] = []
        for overlay_id in requested:
            if overlay_id in available_ids and overlay_id not in selected:
                selected.append(overlay_id)
        return selected

    def _message_requests_map_context(self, user_message: str) -> bool:
        normalized = user_message.lower()
        return any(
            token in normalized
            for token in (
                "map",
                "layer",
                "overlay",
                "traffic",
                "air quality",
                "weather",
                "compare",
                "satellite",
            )
        )

    def _check_ollama_availability(self, settings) -> tuple[bool, str | None]:
        configured_providers = {
            str(settings.chat_model_provider).strip().lower(),
            str(settings.parser_model_provider).strip().lower(),
            str(settings.agent_model_provider).strip().lower(),
        }
        if "ollama" not in configured_providers:
            return True, None
        health = OllamaProvider(base_url=settings.ollama_url).health_check()
        if bool(health.get("ok")):
            return True, None
        detail = str(health.get("detail") or "connection failed").strip()
        return False, detail

    def _catalog_lookup(self, kind: str) -> dict[str, dict[str, Any]]:
        if self.catalog_service is None:
            return {}
        try:
            catalog = self.catalog_service.list_catalog()
        except Exception:
            return {}
        key = "basemaps" if kind == "basemaps" else "overlays"
        return {
            str(item.get("id")): item
            for item in catalog.get(key, [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }

    def _annotate_retrieval_candidates(self, retrieval: dict[str, list[dict[str, object]]]) -> dict[str, list[dict[str, object]]]:
        annotated: dict[str, list[dict[str, object]]] = {"basemaps": [], "overlays": [], "providers": []}
        for kind in ("basemaps", "overlays"):
            lookup = self._catalog_lookup(kind)
            for candidate in retrieval.get(kind, []):
                if not isinstance(candidate, dict):
                    continue
                item_id = str(candidate.get("id") or "").strip()
                if not item_id:
                    continue
                metadata = candidate.get("metadata")
                metadata_dict = metadata if isinstance(metadata, dict) else {}
                catalog_item = lookup.get(item_id, {})
                label = (
                    catalog_item.get("label")
                    or metadata_dict.get("name")
                    or item_id
                )
                provider_name = catalog_item.get("provider") or metadata_dict.get("provider")
                is_available = bool(catalog_item.get("is_available", True))
                availability_reason = catalog_item.get("availability_reason")
                summary = (
                    metadata_dict.get("human_summary")
                    if isinstance(metadata_dict.get("human_summary"), str)
                    else metadata_dict.get("keywords")
                )
                annotated[kind].append(
                    {
                        "id": item_id,
                        "score": float(candidate.get("score", 0.0) or 0.0),
                        "distance": float(candidate.get("distance", 0.0) or 0.0),
                        "label": str(label),
                        "provider": str(provider_name) if provider_name else None,
                        "is_available": is_available,
                        "availability_reason": availability_reason if not is_available else None,
                        "summary": summary,
                    }
                )
        return annotated

    def _overlay_candidates_by_provider(self, overlays: list[dict[str, object]], *, per_provider_limit: int = 3) -> list[dict[str, object]]:
        grouped: dict[str, list[dict[str, object]]] = {}
        for item in overlays:
            if not isinstance(item, dict):
                continue
            provider = str(item.get("provider") or "unknown").strip().lower()
            grouped.setdefault(provider, []).append(item)
        selected: list[dict[str, object]] = []
        for provider_items in grouped.values():
            ranked = sorted(provider_items, key=lambda it: float(it.get("score", 0.0) or 0.0), reverse=True)
            selected.extend(ranked[: max(1, per_provider_limit)])
        return selected

    def _select_direct_tool_from_stage_a(
        self,
        stage_a: StageAParserIntent,
        available_tools: list[dict[str, str]],
    ) -> str | None:
        if stage_a.requires_search:
            return None
        available_names = {str(item.get("name") or "").strip() for item in available_tools}
        for requested in stage_a.required_tools:
            if requested in available_names:
                return requested
        return None

    def _infer_area_of_interest(self, user_message: str) -> str | None:
        match = re.search(r"\b(?:nearby|around|area nearby|around the)\s+(.+)$", user_message.strip(), re.IGNORECASE)
        if not match:
            return None
        value = match.group(1).strip(" .")
        return value or None

    def _build_patch_from_stage_b(self, *, request_message: str, stage_a: StageAParserIntent, stage_b: StageBSearchExtraction) -> dict[str, Any]:
        location_payload: dict[str, Any] | None = None
        if any([stage_b.location.address, stage_b.location.city, stage_b.location.country]):
            location_payload = {
                "address": stage_b.location.address,
                "city": stage_b.location.city,
                "country": stage_b.location.country,
            }
        coordinate_payload: dict[str, Any] | None = None
        if stage_b.coordinates.latitude is not None or stage_b.coordinates.longitude is not None:
            coordinate_payload = {
                "latitude": stage_b.coordinates.latitude,
                "longitude": stage_b.coordinates.longitude,
            }
        return {
            "location": location_payload,
            "coordinates": coordinate_payload,
            "location_type": stage_b.location.location_type or stage_a.location_type,
            "base_map_type": stage_b.base_map,
            "user_goal": request_message.strip(),
            "filters": list(stage_b.required_overlays),
            "area_of_interest": self._infer_area_of_interest(request_message),
            "certainty": stage_a.certainty,
        }

    def _apply_task_scope_to_state(
        self,
        *,
        latest_state: ExtractedIntent,
        merged_state: ExtractedIntent,
        task_scope: TaskScopeDecision,
    ) -> ExtractedIntent:
        if not task_scope.starts_new_task:
            return merged_state
        # Hard reset stale task fields, then keep only current turn extraction.
        reset_state = ExtractedIntent()
        reset_state = reset_state.model_copy(
            update={
                "location": merged_state.location,
                "coordinates": merged_state.coordinates,
                "location_type": merged_state.location_type,
                "base_map_type": merged_state.base_map_type,
                "user_goal": merged_state.user_goal,
                "certainty": merged_state.certainty,
                "area_of_interest": merged_state.area_of_interest,
                "filters": list(merged_state.filters) if task_scope.carry_forward_filters else [],
                "time_references": merged_state.time_references if task_scope.carry_forward_time else reset_state.time_references,
            }
        )
        _ = latest_state
        return reset_state

    def _summarize_retrieval_for_context(self, retrieval: dict[str, list[dict[str, object]]]) -> str:
        basemap_labels = [str(item.get("label") or item.get("id")) for item in retrieval.get("basemaps", []) if isinstance(item, dict)]
        overlay_labels = [str(item.get("label") or item.get("id")) for item in retrieval.get("overlays", []) if isinstance(item, dict)]
        if not basemap_labels and not overlay_labels:
            return ""
        return (
            f"basemaps={', '.join(basemap_labels[:3]) or 'none'}; "
            f"overlays={', '.join(overlay_labels[:6]) or 'none'}"
        )

    async def run_turn(self, request: ChatTurnRequest) -> ChatTurnResponse:
        started = perf_counter()
        settings = self.settings_repo.get_or_create()
        session = self.history_repo.upsert_session(request.session_id, title=request.title)
        user_row = self.history_repo.append_message(session_id=session.id, role="user", content=request.message)
        self.history_buffer.append(
            session.id,
            {
                "id": user_row.id,
                "session_id": session.id,
                "turn_index": user_row.turn_index,
                "role": user_row.role,
                "content": user_row.content,
                "structured_payload": None,
                "tool_payload": None,
                "map_session": None,
                "created_at": user_row.created_at.isoformat() if user_row.created_at else None,
            },
        )

        _history = self.history_buffer.get_or_hydrate(session.id)
        latest_state = self.history_repo.get_latest_extracted_state(session.id) or ExtractedIntent()
        task_scope = self.task_scope_service.decide_scope(
            history=_history,
            user_message=request.message,
            latest_state=latest_state,
        )
        scoped_history = self.history_buffer.list_scoped(
            session.id,
            start_index=task_scope.history_start_index,
        )
        carry_state = latest_state if not task_scope.starts_new_task else ExtractedIntent()
        ollama_ok, ollama_detail = self._check_ollama_availability(settings)
        if not ollama_ok:
            assistant_message = (
                "I cannot reach your local Ollama service right now, so I cannot process this request with the current model settings. "
                f"Please start Ollama at {settings.ollama_url} or switch to a cloud model in Settings, then try again."
            )
            assistant_row = self.history_repo.append_message(
                session_id=session.id,
                role="assistant",
                content=assistant_message,
                structured_payload=latest_state.model_dump(mode="json"),
                tool_payload={"execution": "provider_error", "provider": "ollama", "detail": ollama_detail},
                map_session=None,
            )
            self.history_buffer.append(
                session.id,
                {
                    "id": assistant_row.id,
                    "session_id": session.id,
                    "turn_index": assistant_row.turn_index,
                    "role": assistant_row.role,
                    "content": assistant_row.content,
                    "structured_payload": latest_state.model_dump(mode="json"),
                    "tool_payload": {"execution": "provider_error", "provider": "ollama", "detail": ollama_detail},
                    "map_session": None,
                    "created_at": assistant_row.created_at.isoformat() if assistant_row.created_at else None,
                },
            )
            elapsed = perf_counter() - started
            self.session_catalog_repo.upsert_for_session(
                session_id=session.id,
                models={
                    "parser": {"provider": settings.parser_model_provider, "name": settings.parser_model_name},
                    "agent": {"provider": settings.agent_model_provider, "name": settings.agent_model_name},
                    "chat": {"provider": settings.chat_model_provider, "name": settings.chat_model_name},
                },
            )
            self.session_details_repo.insert_turn(
                session_id=session.id,
                message_id=assistant_row.id,
                user_message=request.message,
                chat_response=assistant_message,
                extracted_info=latest_state.model_dump(mode="json"),
                response_time=elapsed,
                has_triggered_search=False,
            )
            return ChatTurnResponse(
                session_id=session.id,
                assistant_message=assistant_message,
                structured_intent=latest_state.model_dump(mode="json"),
                extracted_state=latest_state.model_dump(mode="json"),
                map_session=None,
                tool_payload={"execution": "provider_error", "provider": "ollama", "detail": ollama_detail},
                follow_up_required=False,
                fallback_mode="provider_unavailable",
            )
        latest_extracted_info = carry_state.model_dump_json(indent=2)
        initial_context = build_conversation_context(
            messages=scoped_history,
            extracted_info=latest_extracted_info,
            max_messages=get_server_settings().chat.max_history_messages,
            history_start_index=0,
            current_user_message=request.message,
        )

        parser_service = ParserService(
            llm_factory=self.llm_factory,
            provider=settings.parser_model_provider,
            model=settings.parser_model_name,
        )
        decision_service = DecisionService(
            llm_factory=self.llm_factory,
            provider=settings.agent_model_provider,
            model=settings.agent_model_name,
        )
        chat_service = ChatResponseService(
            llm_factory=self.llm_factory,
            provider=settings.chat_model_provider,
            model=settings.chat_model_name,
        )

        available_tools = self.agent_tools.describe_tools() if self.agent_tools is not None else []
        stage_a = parser_service.parse_stage_a_intent(
            conversation_context=initial_context,
            user_message=request.message,
            available_tools=available_tools,
            certainty_threshold=get_server_settings().chat.parser_certainty_threshold,
            max_retries=get_server_settings().chat.parser_max_retries,
        )
        retrieval: dict[str, list[dict[str, object]]] = {"basemaps": [], "overlays": [], "providers": []}
        if stage_a.requires_data or stage_a.requires_search:
            try:
                retrieval = self.vector_retriever.retrieve_candidates(
                    request.message.strip(),
                    top_k=10,
                    basemap_k=1,
                    overlay_k=10,
                )
            except TypeError:
                retrieval = self.vector_retriever.retrieve_candidates(
                    request.message.strip(),
                    top_k=10,
                )
        annotated_retrieval = self._annotate_retrieval_candidates(retrieval)
        annotated_retrieval["overlays"] = self._overlay_candidates_by_provider(annotated_retrieval.get("overlays", []))
        if annotated_retrieval.get("basemaps"):
            annotated_retrieval["basemaps"] = sorted(
                annotated_retrieval["basemaps"],
                key=lambda item: float(item.get("score", 0.0) or 0.0),
                reverse=True,
            )[:1]
        stage_b = parser_service.parse_stage_b_enrichment(
            conversation_context=initial_context,
            user_message=request.message,
            retrieval=annotated_retrieval,
            fallback_datetime=request.datetime or datetime.now(UTC).isoformat(),
        )
        patch_payload = self._build_patch_from_stage_b(
            request_message=request.message,
            stage_a=stage_a,
            stage_b=stage_b,
        )
        patch = ExtractedIntentPatch.model_validate(patch_payload)
        extracted_state = merge_extracted_intent(carry_state, patch)
        extracted_state = self._apply_task_scope_to_state(
            latest_state=latest_state,
            merged_state=extracted_state,
            task_scope=task_scope,
        )
        extracted_state = self._normalize_extracted_state_for_turn(
            extracted_state=extracted_state,
            user_message=request.message,
        )
        context = build_conversation_context(
            messages=scoped_history,
            extracted_info=ExtractedIntent.model_validate(extracted_state).model_dump_json(indent=2),
            max_messages=get_server_settings().chat.max_history_messages,
            history_start_index=0,
            current_user_message=request.message,
            retrieval_summary=self._summarize_retrieval_for_context(annotated_retrieval),
        )

        if not stage_a.has_location:
            decision = decision_service._build_missing_location_decision()
        elif not stage_a.requires_search:
            direct_tool = self._select_direct_tool_from_stage_a(stage_a, available_tools)
            if direct_tool:
                if direct_tool == "location_to_coordinates":
                    decision = decision_service._build_geocode_decision(
                        has_text_location=bool(stage_b.location.address or stage_b.location.city or stage_b.location.country),
                        has_coordinates=bool(stage_b.coordinates.latitude is not None and stage_b.coordinates.longitude is not None),
                    )
                else:
                    decision = decision_service._build_direct_tool_decision(
                        tool_target=direct_tool,
                        has_text_location=bool(stage_b.location.address or stage_b.location.city or stage_b.location.country),
                        has_coordinates=bool(stage_b.coordinates.latitude is not None and stage_b.coordinates.longitude is not None),
                        summary="Routed from parser required_tools",
                    )
            else:
                decision = decision_service.decide(
                    conversation_context=context,
                    user_message=request.message,
                    extracted_state=extracted_state,
                    retrieval=annotated_retrieval,
                    available_tools=available_tools,
                )
        else:
            has_coordinates = (
                stage_b.coordinates.latitude is not None
                and stage_b.coordinates.longitude is not None
            )
            if stage_a.requires_search and has_coordinates:
                decision = decision_service.decide(
                    conversation_context=context,
                    user_message=request.message,
                    extracted_state=extracted_state,
                    retrieval=annotated_retrieval,
                    available_tools=available_tools,
                )
                decision = decision.model_copy(
                    update={
                        "execution_mode": "search",
                        "tool_target": "map_search",
                        "should_trigger_search": True,
                        "decision": "search_and_complete",
                    }
                )
            else:
                decision = decision_service.decide(
                    conversation_context=context,
                    user_message=request.message,
                    extracted_state=extracted_state,
                    retrieval=annotated_retrieval,
                    available_tools=available_tools,
                )
        if decision.execution_mode == "search" and decision.should_trigger_search and not decision.selected_basemap_id:
            top_basemap = annotated_retrieval.get("basemaps", [])
            if top_basemap:
                decision = decision.model_copy(update={"selected_basemap_id": str(top_basemap[0].get("id") or "") or None})
        if (
            decision.execution_mode == "search"
            and decision.should_trigger_search
            and not decision.selected_overlay_ids
        ):
            inferred_overlay_ids = self._fallback_overlay_ids_from_retrieval(
                user_message=request.message,
                stage_b=stage_b,
                retrieval=annotated_retrieval,
            )
            if inferred_overlay_ids:
                decision = decision.model_copy(update={"selected_overlay_ids": inferred_overlay_ids})
        self._debug_log(
            "decision",
            {
                "session_id": session.id,
                "decision": decision.model_dump(mode="json"),
            },
        )

        search_result: dict[str, Any] | None = None
        map_session: dict[str, Any] | None = None
        tool_payload: dict[str, Any] | None = None
        execution_feedback: dict[str, Any] = {"status": "pending", "errors": [], "ambiguities": []}
        if decision.execution_mode == "search" and decision.should_trigger_search:
            mapped_payload = map_structured_intent_to_location_request(
                extracted_state=extracted_state.model_dump(mode="json"),
                user_message=request.message,
                selected_basemap_id=decision.selected_basemap_id,
                selected_overlay_ids=decision.selected_overlay_ids,
                fallback_datetime=request.datetime or datetime.now(UTC).isoformat(),
            )
            location_request = LocationSearchRequest.model_validate(mapped_payload)
            search_result = await self.search_orchestrator.execute(location_request)
            map_session = search_result.get("map_session")
            search_payload = search_result.get("payload") if isinstance(search_result.get("payload"), dict) else {}
            tool_payload = {
                "execution": "map_search",
                "selected_overlay_ids": list(search_payload.get("selected_overlay_ids") or decision.selected_overlay_ids),
                "applied_filters": list(search_payload.get("applied_filters") or []),
                "unmet_filters": list(search_payload.get("unmet_filters") or []),
                "fallback_mode": search_payload.get("fallback_mode"),
            }
            execution_feedback = {"status": "success", "errors": [], "ambiguities": []}
        elif decision.execution_mode == "geocode":
            if (
                extracted_state.coordinates.latitude is not None
                and extracted_state.coordinates.longitude is not None
                and not any(
                    [
                        extracted_state.location.address,
                        extracted_state.location.city,
                        extracted_state.location.country,
                    ]
                )
            ):
                geocode_result = {
                    "lat": extracted_state.coordinates.latitude,
                    "lon": extracted_state.coordinates.longitude,
                    "display_name": "Coordinates from your request",
                }
            else:
                location_query = self._derive_location_query_from_message(request.message)
                geocode_address = extracted_state.location.address or location_query
                geocode_result = (
                    await self.agent_tools.geocode_location(
                        address=geocode_address,
                        city=extracted_state.location.city,
                        country_name=extracted_state.location.country,
                        expected_location_type=extracted_state.location_type,
                    )
                    if self.agent_tools is not None
                    else None
                )
            search_result = {"geocode_result": geocode_result}
            tool_payload = {
                "execution": "location_to_coordinates",
                "result": geocode_result,
                "fallback_mode": "geocode_failed" if geocode_result is None else None,
            }
            execution_feedback = {
                "status": "success" if geocode_result is not None else "failure",
                "errors": [] if geocode_result is not None else ["geocode_failed"],
                "ambiguities": [] if geocode_result is not None else ["location_unresolved"],
            }
            if (
                isinstance(geocode_result, dict)
                and geocode_result.get("lat") is not None
                and geocode_result.get("lon") is not None
                and self._message_requests_map_context(request.message)
            ):
                inferred_overlay_ids = (
                    decision.selected_overlay_ids
                    if decision.selected_overlay_ids
                    else self._fallback_overlay_ids_from_retrieval(
                        user_message=request.message,
                        stage_b=stage_b,
                        retrieval=annotated_retrieval,
                    )
                )
                promoted_payload = LocationSearchRequest.model_validate(
                    {
                        "datetime": request.datetime or datetime.now(UTC).isoformat(),
                        "use_coordinates": True,
                        "latitude": float(geocode_result["lat"]),
                        "longitude": float(geocode_result["lon"]),
                        "filters": [],
                        "semantic_filters": list(extracted_state.filters),
                        "overlay_ids": list(inferred_overlay_ids),
                        "basemap_id": decision.selected_basemap_id,
                        "map_size_m": get_server_settings().map.default_size_m,
                        "image_crs": "EPSG:3857",
                    }
                )
                promoted_search = await self.search_orchestrator.execute(promoted_payload)
                promoted_payload_data = (
                    promoted_search.get("payload")
                    if isinstance(promoted_search.get("payload"), dict)
                    else {}
                )
                map_session = promoted_search.get("map_session")
                search_result = promoted_search
                tool_payload = {
                    "execution": "map_search",
                    "selected_overlay_ids": list(promoted_payload_data.get("selected_overlay_ids") or inferred_overlay_ids),
                    "applied_filters": list(promoted_payload_data.get("applied_filters") or extracted_state.filters),
                    "unmet_filters": list(promoted_payload_data.get("unmet_filters") or []),
                    "fallback_mode": promoted_payload_data.get("fallback_mode"),
                }
                execution_feedback = {"status": "success", "errors": [], "ambiguities": []}
                decision = decision.model_copy(
                    update={
                        "decision": "search_and_complete",
                        "execution_mode": "search",
                        "tool_target": "map_search",
                        "should_trigger_search": True,
                        "requires_geocoding": False,
                    }
                )
        elif decision.execution_mode == "search" and not decision.should_trigger_search:
            tool_target = str(decision.tool_target or "").strip()
            direct_tool_targets = {"get_weather_forecast", "get_air_quality_forecast", "get_nearby_poi"}
            if tool_target in direct_tool_targets and self.agent_tools is not None:
                latitude = extracted_state.coordinates.latitude
                longitude = extracted_state.coordinates.longitude
                if latitude is None or longitude is None:
                    geocode_result = await self.agent_tools.geocode_location(
                        address=extracted_state.location.address,
                        city=extracted_state.location.city,
                        country_name=extracted_state.location.country,
                        expected_location_type=extracted_state.location_type,
                    )
                    if isinstance(geocode_result, dict):
                        latitude = geocode_result.get("lat")
                        longitude = geocode_result.get("lon")
                if latitude is None or longitude is None:
                    tool_payload = {
                        "execution": "follow_up",
                        "fallback_mode": "missing_location",
                    }
                    execution_feedback = {
                        "status": "failure",
                        "errors": ["missing_location"],
                        "ambiguities": ["location_required"],
                    }
                else:
                    if tool_target == "get_weather_forecast":
                        direct_result = await self.agent_tools.get_weather_forecast(
                            latitude=float(latitude),
                            longitude=float(longitude),
                        )
                    elif tool_target == "get_air_quality_forecast":
                        direct_result = await self.agent_tools.get_air_quality_forecast(
                            latitude=float(latitude),
                            longitude=float(longitude),
                        )
                    else:
                        direct_result = await self.agent_tools.get_nearby_poi(
                            latitude=float(latitude),
                            longitude=float(longitude),
                            radius_m=2500.0,
                        )
                    search_result = {
                        "tool_result": direct_result,
                        "resolved_coordinates": {"lat": float(latitude), "lon": float(longitude)},
                    }
                    tool_payload = {
                        "execution": tool_target,
                        "result": direct_result,
                    }
                    execution_feedback = {"status": "success", "errors": [], "ambiguities": []}
        elif decision.execution_mode == "clarify":
            tool_payload = {"execution": "follow_up", "fallback_mode": "missing_location"}
            execution_feedback = {
                "status": "failure",
                "errors": ["needs_clarification"],
                "ambiguities": [decision.clarification_question or "missing_information"],
            }

        try:
            assistant_message = chat_service.generate(
                conversation_context=context,
                user_message=request.message,
                extracted_state=extracted_state,
                decision=decision,
                retrieval=annotated_retrieval,
                search_result=search_result,
                execution_feedback=execution_feedback,
            )
        except TypeError:
            assistant_message = chat_service.generate(
                conversation_context=context,
                user_message=request.message,
                extracted_state=extracted_state,
                decision=decision,
                retrieval=annotated_retrieval,
                search_result=search_result,
            )
        self._debug_log(
            "turn_outcome",
            {
                "session_id": session.id,
                "map_center": map_session.get("center") if isinstance(map_session, dict) else None,
                "tool_payload": tool_payload,
                "follow_up": decision.execution_mode == "clarify",
            },
        )
        assistant_row = self.history_repo.append_message(
            session_id=session.id,
            role="assistant",
            content=assistant_message,
            structured_payload={
                "stage_a": stage_a.model_dump(mode="json"),
                "stage_b": stage_b.model_dump(mode="json"),
                "decision": decision.model_dump(mode="json"),
                "task_scope": task_scope.model_dump(mode="json"),
                "extracted_state": extracted_state.model_dump(mode="json"),
            },
            tool_payload=tool_payload,
            map_session=map_session,
        )
        self.history_buffer.append(
            session.id,
            {
                "id": assistant_row.id,
                "session_id": session.id,
                "turn_index": assistant_row.turn_index,
                "role": assistant_row.role,
                "content": assistant_row.content,
                "structured_payload": {
                    "stage_a": stage_a.model_dump(mode="json"),
                    "stage_b": stage_b.model_dump(mode="json"),
                    "decision": decision.model_dump(mode="json"),
                    "task_scope": task_scope.model_dump(mode="json"),
                    "extracted_state": extracted_state.model_dump(mode="json"),
                },
                "tool_payload": tool_payload,
                "map_session": map_session,
                "created_at": assistant_row.created_at.isoformat() if assistant_row.created_at else None,
            },
        )

        elapsed = perf_counter() - started
        self.session_catalog_repo.upsert_for_session(
            session_id=session.id,
            models={
                "parser": {"provider": settings.parser_model_provider, "name": settings.parser_model_name},
                "agent": {"provider": settings.agent_model_provider, "name": settings.agent_model_name},
                "chat": {"provider": settings.chat_model_provider, "name": settings.chat_model_name},
            },
        )
        self.session_details_repo.insert_turn(
            session_id=session.id,
            message_id=assistant_row.id,
            user_message=request.message,
            chat_response=assistant_message,
            extracted_info={
                "stage_a": stage_a.model_dump(mode="json"),
                "stage_b": stage_b.model_dump(mode="json"),
                "task_scope": task_scope.model_dump(mode="json"),
            },
            response_time=elapsed,
            has_triggered_search=decision.should_trigger_search,
        )

        follow_up_required = (
            decision.execution_mode == "clarify"
            or decision.decision == "search_with_follow_up"
            or (isinstance(tool_payload, dict) and tool_payload.get("execution") == "follow_up")
        )
        fallback_mode = "needs_clarification" if follow_up_required else "none"
        return ChatTurnResponse(
            session_id=session.id,
            assistant_message=assistant_message,
            structured_intent={
                "stage_a": stage_a.model_dump(mode="json"),
                "stage_b": stage_b.model_dump(mode="json"),
                "task_scope": task_scope.model_dump(mode="json"),
            },
            extracted_state=extracted_state.model_dump(mode="json"),
            map_session=map_session,
            tool_payload=tool_payload,
            follow_up_required=follow_up_required,
            fallback_mode=fallback_mode,
        )
