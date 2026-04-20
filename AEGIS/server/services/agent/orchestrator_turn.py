from __future__ import annotations

import re
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from AEGIS.server.configurations import get_server_settings
from AEGIS.server.domain.chat import ChatTurnRequest, ChatTurnResponse
from AEGIS.server.domain.extraction.models import ExtractedIntent, ExtractedIntentPatch
from AEGIS.server.domain.geographics import LocationSearchRequest
from AEGIS.server.services.agent.chat_response_service import ChatResponseService
from AEGIS.server.services.agent.decision_service import DecisionService
from AEGIS.server.services.agent.parser_service import ParserService
from AEGIS.server.services.llm.context_builder import build_conversation_context
from AEGIS.server.services.search.intent_mapper import map_structured_intent_to_location_request
from AEGIS.server.domain.extraction.patching import merge_extracted_intent


def _coerce_float(value: object, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


async def run_turn_impl(
    orchestrator: Any, request: ChatTurnRequest
) -> ChatTurnResponse:
    started = perf_counter()
    settings = orchestrator.settings_repo.get_or_create()
    session = orchestrator.history_repo.upsert_session(
        request.session_id, title=request.title
    )
    user_row = orchestrator.history_repo.append_message(
        session_id=session.id, role="user", content=request.message
    )
    orchestrator.history_buffer.append(
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
            "created_at": user_row.created_at.isoformat()
            if user_row.created_at
            else None,
        },
    )

    _history = orchestrator.history_buffer.get_or_hydrate(session.id)
    latest_state = (
        orchestrator.history_repo.get_latest_extracted_state(session.id)
        or ExtractedIntent()
    )
    task_scope = orchestrator.task_scope_service.decide_scope(
        history=_history,
        user_message=request.message,
        latest_state=latest_state,
    )
    scoped_history = orchestrator.history_buffer.list_scoped(
        session.id,
        start_index=task_scope.history_start_index,
    )
    carry_state = (
        latest_state if not task_scope.starts_new_task else ExtractedIntent()
    )
    ollama_ok, ollama_detail = orchestrator._check_ollama_availability(settings)
    if not ollama_ok:
        assistant_message = (
            "I cannot reach your local Ollama service right now, so I cannot process this request with the current model settings. "
            f"Please start Ollama at {settings.ollama_url} or switch to a cloud model in Settings, then try again."
        )
        assistant_row = orchestrator.history_repo.append_message(
            session_id=session.id,
            role="assistant",
            content=assistant_message,
            structured_payload=latest_state.model_dump(mode="json"),
            tool_payload={
                "execution": "provider_error",
                "provider": "ollama",
                "detail": ollama_detail,
            },
            map_session=None,
        )
        orchestrator.history_buffer.append(
            session.id,
            {
                "id": assistant_row.id,
                "session_id": session.id,
                "turn_index": assistant_row.turn_index,
                "role": assistant_row.role,
                "content": assistant_row.content,
                "structured_payload": latest_state.model_dump(mode="json"),
                "tool_payload": {
                    "execution": "provider_error",
                    "provider": "ollama",
                    "detail": ollama_detail,
                },
                "map_session": None,
                "created_at": assistant_row.created_at.isoformat()
                if assistant_row.created_at
                else None,
            },
        )
        elapsed = perf_counter() - started
        orchestrator.session_catalog_repo.upsert_for_session(
            session_id=session.id,
            models={
                "parser": {
                    "provider": settings.parser_model_provider,
                    "name": settings.parser_model_name,
                },
                "agent": {
                    "provider": settings.agent_model_provider,
                    "name": settings.agent_model_name,
                },
                "chat": {
                    "provider": settings.chat_model_provider,
                    "name": settings.chat_model_name,
                },
            },
        )
        orchestrator.session_details_repo.insert_turn(
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
            tool_payload={
                "execution": "provider_error",
                "provider": "ollama",
                "detail": ollama_detail,
            },
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
        llm_factory=orchestrator.llm_factory,
        provider=settings.parser_model_provider,
        model=settings.parser_model_name,
    )
    decision_service = DecisionService(
        llm_factory=orchestrator.llm_factory,
        provider=settings.agent_model_provider,
        model=settings.agent_model_name,
    )
    chat_service = ChatResponseService(
        llm_factory=orchestrator.llm_factory,
        provider=settings.chat_model_provider,
        model=settings.chat_model_name,
    )

    available_tools = (
        orchestrator.agent_tools.describe_tools() if orchestrator.agent_tools is not None else []
    )
    stage_a = parser_service.parse_stage_a_intent(
        conversation_context=initial_context,
        user_message=request.message,
        available_tools=available_tools,
        certainty_threshold=get_server_settings().chat.parser_certainty_threshold,
        max_retries=get_server_settings().chat.parser_max_retries,
    )
    retrieval: dict[str, list[dict[str, object]]] = {
        "basemaps": [],
        "overlays": [],
        "providers": [],
    }
    if stage_a.requires_data or stage_a.requires_search:
        try:
            retrieval = orchestrator.vector_retriever.retrieve_candidates(
                request.message.strip(),
                top_k=10,
                basemap_k=1,
                overlay_k=10,
            )
        except TypeError:
            retrieval = orchestrator.vector_retriever.retrieve_candidates(
                request.message.strip(),
                top_k=10,
            )
    annotated_retrieval = orchestrator._annotate_retrieval_candidates(retrieval)
    annotated_retrieval["overlays"] = orchestrator._overlay_candidates_by_provider(
        annotated_retrieval.get("overlays", [])
    )
    if annotated_retrieval.get("basemaps"):
        annotated_retrieval["basemaps"] = sorted(
            annotated_retrieval["basemaps"],
            key=lambda item: _coerce_float(item.get("score", 0.0)),
            reverse=True,
        )[:1]
    stage_b = parser_service.parse_stage_b_enrichment(
        conversation_context=initial_context,
        user_message=request.message,
        retrieval=annotated_retrieval,
        fallback_datetime=request.datetime or datetime.now(UTC).isoformat(),
    )
    patch_payload = orchestrator._build_patch_from_stage_b(
        request_message=request.message,
        stage_a=stage_a,
        stage_b=stage_b,
    )
    patch = ExtractedIntentPatch.model_validate(patch_payload)
    extracted_state = merge_extracted_intent(carry_state, patch)
    extracted_state = orchestrator._apply_task_scope_to_state(
        latest_state=latest_state,
        merged_state=extracted_state,
        task_scope=task_scope,
    )
    extracted_state = orchestrator._normalize_extracted_state_for_turn(
        extracted_state=extracted_state,
        user_message=request.message,
    )
    context = build_conversation_context(
        messages=scoped_history,
        extracted_info=ExtractedIntent.model_validate(
            extracted_state
        ).model_dump_json(indent=2),
        max_messages=get_server_settings().chat.max_history_messages,
        history_start_index=0,
        current_user_message=request.message,
        retrieval_summary=orchestrator._summarize_retrieval_for_context(
            annotated_retrieval
        ),
    )

    if not stage_a.has_location:
        decision = decision_service._build_missing_location_decision()
    elif not stage_a.requires_search:
        direct_tool = orchestrator._select_direct_tool_from_stage_a(
            stage_a, available_tools
        )
        if direct_tool:
            if direct_tool == "location_to_coordinates":
                decision = decision_service._build_geocode_decision(
                    has_text_location=bool(
                        stage_b.location.address
                        or stage_b.location.city
                        or stage_b.location.country
                    ),
                    has_coordinates=bool(
                        stage_b.coordinates.latitude is not None
                        and stage_b.coordinates.longitude is not None
                    ),
                )
            else:
                decision = decision_service._build_direct_tool_decision(
                    tool_target=direct_tool,
                    has_text_location=bool(
                        stage_b.location.address
                        or stage_b.location.city
                        or stage_b.location.country
                    ),
                    has_coordinates=bool(
                        stage_b.coordinates.latitude is not None
                        and stage_b.coordinates.longitude is not None
                    ),
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
    if (
        decision.execution_mode == "search"
        and decision.should_trigger_search
        and not decision.selected_basemap_id
    ):
        top_basemap = annotated_retrieval.get("basemaps", [])
        if top_basemap:
            decision = decision.model_copy(
                update={
                    "selected_basemap_id": str(top_basemap[0].get("id") or "")
                    or None
                }
            )
    if (
        decision.execution_mode == "search"
        and decision.should_trigger_search
        and not decision.selected_overlay_ids
    ):
        inferred_overlay_ids = orchestrator._fallback_overlay_ids_from_retrieval(
            user_message=request.message,
            stage_b=stage_b,
            retrieval=annotated_retrieval,
        )
        if inferred_overlay_ids:
            decision = decision.model_copy(
                update={"selected_overlay_ids": inferred_overlay_ids}
            )
    orchestrator._debug_log(
        "decision",
        {
            "session_id": session.id,
            "decision": decision.model_dump(mode="json"),
        },
    )

    search_result: dict[str, Any] | None = None
    map_session: dict[str, Any] | None = None
    tool_payload: dict[str, Any] | None = None
    execution_feedback: dict[str, Any] = {
        "status": "pending",
        "errors": [],
        "ambiguities": [],
    }
    if decision.execution_mode == "search" and decision.should_trigger_search:
        mapped_payload = map_structured_intent_to_location_request(
            extracted_state=extracted_state.model_dump(mode="json"),
            user_message=request.message,
            selected_basemap_id=decision.selected_basemap_id,
            selected_overlay_ids=decision.selected_overlay_ids,
            fallback_datetime=request.datetime or datetime.now(UTC).isoformat(),
        )
        location_request = LocationSearchRequest.model_validate(mapped_payload)
        search_result = await orchestrator.search_orchestrator.execute(location_request)
        map_session = search_result.get("map_session")
        search_payload = _as_dict(search_result.get("payload"))
        tool_payload = {
            "execution": "map_search",
            "selected_overlay_ids": list(
                search_payload.get("selected_overlay_ids")
                or decision.selected_overlay_ids
            ),
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
            location_query = orchestrator._derive_location_query_from_message(
                request.message
            )
            geocode_address = location_query or extracted_state.location.address
            geocode_city = extracted_state.location.city
            geocode_country = extracted_state.location.country
            geocode_result = None
            if orchestrator.agent_tools is not None:
                geocode_result = await orchestrator.agent_tools.geocode_location(
                    address=geocode_address,
                    city=geocode_city,
                    country_name=geocode_country,
                    expected_location_type=extracted_state.location_type,
                )
                if geocode_result is None and isinstance(location_query, str):
                    split_match = re.search(
                        r"^(.+?)\s+in\s+([a-z0-9][a-z0-9\s,'\\-]{2,})$",
                        location_query.strip(),
                        re.IGNORECASE,
                    )
                    if split_match:
                        retry_address = split_match.group(1).strip(" .")
                        retry_city = split_match.group(2).strip(" .")
                        geocode_result = await orchestrator.agent_tools.geocode_location(
                            address=retry_address,
                            city=retry_city,
                            country_name=geocode_country,
                            expected_location_type=extracted_state.location_type,
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
            "ambiguities": []
            if geocode_result is not None
            else ["location_unresolved"],
        }
        if (
            isinstance(geocode_result, dict)
            and geocode_result.get("lat") is not None
            and geocode_result.get("lon") is not None
            and orchestrator._message_requests_map_context(request.message)
        ):
            inferred_overlay_ids = (
                decision.selected_overlay_ids
                if decision.selected_overlay_ids
                else orchestrator._fallback_overlay_ids_from_retrieval(
                    user_message=request.message,
                    stage_b=stage_b,
                    retrieval=annotated_retrieval,
                )
            )
            promoted_payload = LocationSearchRequest.model_validate(
                {
                    "datetime": request.datetime or datetime.now(UTC).isoformat(),
                    "use_coordinates": True,
                    "latitude": _coerce_float(geocode_result["lat"]),
                    "longitude": _coerce_float(geocode_result["lon"]),
                    "filters": [],
                    "semantic_filters": list(extracted_state.filters),
                    "overlay_ids": list(inferred_overlay_ids),
                    "basemap_id": decision.selected_basemap_id,
                    "map_size_m": get_server_settings().map.default_size_m,
                    "image_crs": "EPSG:3857",
                }
            )
            promoted_search = await orchestrator.search_orchestrator.execute(
                promoted_payload
            )
            promoted_payload_data = _as_dict(promoted_search.get("payload"))
            map_session = promoted_search.get("map_session")
            search_result = promoted_search
            tool_payload = {
                "execution": "map_search",
                "selected_overlay_ids": list(
                    promoted_payload_data.get("selected_overlay_ids")
                    or inferred_overlay_ids
                ),
                "applied_filters": list(
                    promoted_payload_data.get("applied_filters")
                    or extracted_state.filters
                ),
                "unmet_filters": list(
                    promoted_payload_data.get("unmet_filters") or []
                ),
                "fallback_mode": promoted_payload_data.get("fallback_mode"),
            }
            execution_feedback = {
                "status": "success",
                "errors": [],
                "ambiguities": [],
            }
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
        direct_tool_targets = {
            "get_weather_forecast",
            "get_air_quality_forecast",
            "get_nearby_poi",
        }
        if tool_target in direct_tool_targets and orchestrator.agent_tools is not None:
            latitude = extracted_state.coordinates.latitude
            longitude = extracted_state.coordinates.longitude
            if latitude is None or longitude is None:
                geocode_result = await orchestrator.agent_tools.geocode_location(
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
                    direct_result = await orchestrator.agent_tools.get_weather_forecast(
                        latitude=_coerce_float(latitude),
                        longitude=_coerce_float(longitude),
                    )
                elif tool_target == "get_air_quality_forecast":
                    direct_result = await orchestrator.agent_tools.get_air_quality_forecast(
                        latitude=_coerce_float(latitude),
                        longitude=_coerce_float(longitude),
                    )
                else:
                    direct_result = await orchestrator.agent_tools.get_nearby_poi(
                        latitude=_coerce_float(latitude),
                        longitude=_coerce_float(longitude),
                        radius_m=2500.0,
                    )
                search_result = {
                    "tool_result": direct_result,
                    "resolved_coordinates": {
                        "lat": _coerce_float(latitude),
                        "lon": _coerce_float(longitude),
                    },
                }
                tool_payload = {
                    "execution": tool_target,
                    "result": direct_result,
                }
                execution_feedback = {
                    "status": "success",
                    "errors": [],
                    "ambiguities": [],
                }
    elif decision.execution_mode == "clarify":
        tool_payload = {
            "execution": "follow_up",
            "fallback_mode": "missing_location",
        }
        execution_feedback = {
            "status": "failure",
            "errors": ["needs_clarification"],
            "ambiguities": [
                decision.clarification_question or "missing_information"
            ],
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
    orchestrator._debug_log(
        "turn_outcome",
        {
            "session_id": session.id,
            "map_center": map_session.get("center")
            if isinstance(map_session, dict)
            else None,
            "tool_payload": tool_payload,
            "follow_up": decision.execution_mode == "clarify",
        },
    )
    assistant_row = orchestrator.history_repo.append_message(
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
    orchestrator.history_buffer.append(
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
            "created_at": assistant_row.created_at.isoformat()
            if assistant_row.created_at
            else None,
        },
    )

    elapsed = perf_counter() - started
    orchestrator.session_catalog_repo.upsert_for_session(
        session_id=session.id,
        models={
            "parser": {
                "provider": settings.parser_model_provider,
                "name": settings.parser_model_name,
            },
            "agent": {
                "provider": settings.agent_model_provider,
                "name": settings.agent_model_name,
            },
            "chat": {
                "provider": settings.chat_model_provider,
                "name": settings.chat_model_name,
            },
        },
    )
    orchestrator.session_details_repo.insert_turn(
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
        or (
            isinstance(tool_payload, dict)
            and tool_payload.get("execution") == "follow_up"
        )
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
