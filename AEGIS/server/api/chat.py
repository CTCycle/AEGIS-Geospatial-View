from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from AEGIS.server.domain.chat import (
    ChatStreamEvent,
    ChatTurnRequest,
    ChatTurnResponse,
    ModelLibraryResponse,
    ModelSettingsResponse,
    ModelSettingsUpdateRequest,
    OllamaHealthResponse,
    OllamaPullRequest,
    OllamaPullResponse,
    OllamaRefreshResponse,
    VectorizationResponse,
)
from AEGIS.server.services.llm.errors import LLMConfigurationError
from AEGIS.server.services.chat.composition import ChatRuntime
from AEGIS.server.common.constants import (
    CHAT_MODELS_ROUTE,
    CHAT_OLLAMA_HEALTH_ROUTE,
    CHAT_OLLAMA_PULL_ROUTE,
    CHAT_OLLAMA_REFRESH_ROUTE,
    CHAT_ROUTER_PREFIX,
    CHAT_SETTINGS_ROUTE,
    CHAT_STREAM_ROUTE,
    CHAT_TURN_ROUTE,
    CHAT_VECTORS_REBUILD_ROUTE,
    CHAT_VECTORS_SYNC_ROUTE,
)

router = APIRouter(prefix=CHAT_ROUTER_PREFIX, tags=["chat"])
logger = logging.getLogger(__name__)

###############################################################################
def get_chat_runtime(request: Request) -> ChatRuntime:
    return request.app.state.chat_runtime


###############################################################################
def _build_tool_status_payload(tool_payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(tool_payload, dict):
        return {"available": False}
    satellite_imagery = tool_payload.get("satellite_imagery")
    map_session = tool_payload.get("map_session")
    overlay_count = 0
    if isinstance(map_session, dict):
        overlays = map_session.get("overlays")
        if isinstance(overlays, list):
            overlay_count = len(overlays)
    return {
        "available": True,
        "execution": tool_payload.get("execution"),
        "has_satellite_imagery": isinstance(satellite_imagery, dict),
        "has_map_session": isinstance(map_session, dict),
        "overlay_count": overlay_count,
    }


###############################################################################
def _stream_event(event: ChatStreamEvent) -> str:
    return json.dumps(event.model_dump(mode="json")) + "\n"


def _ensure_request_id(payload: ChatTurnRequest) -> ChatTurnRequest:
    if payload.request_id:
        return payload
    return payload.model_copy(update={"request_id": f"chat-{uuid4().hex[:12]}"})


###############################################################################
async def _chat_event_stream(
    payload: ChatTurnRequest,
    runtime: ChatRuntime,
) -> AsyncIterator[str]:
    payload = _ensure_request_id(payload)
    request_id = payload.request_id
    yield _stream_event(
        ChatStreamEvent(
            event="status",
            data={"message": "received", "request_id": request_id or ""},
        )
    )
    try:
        result = await runtime.agent_orchestrator.run_turn(payload)
        request_id = result.request_id
        for token in result.assistant_message.split():
            yield _stream_event(
                ChatStreamEvent(event="assistant_delta", data={"delta": f"{token} "})
            )
        if result.tool_payload is not None:
            yield _stream_event(
                ChatStreamEvent(
                    event="tool_status",
                    data=_build_tool_status_payload(result.tool_payload),
                )
            )
        yield _stream_event(
            ChatStreamEvent(
                event="final",
                data={
                    "session_id": result.session_id,
                    "request_id": result.request_id,
                    "assistant_message": result.assistant_message,
                    "turn_contract": result.turn_contract.model_dump(mode="json"),
                    "decision": result.decision.model_dump(mode="json"),
                    "map_session": result.map_session.model_dump(mode="json")
                    if result.map_session is not None
                    else None,
                    "tool_payload": result.tool_payload,
                    "memory_snapshot": result.memory_snapshot,
                },
            )
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
        yield _stream_event(
            ChatStreamEvent(
                event="error",
                data={"message": detail, "status": exc.status_code, "request_id": request_id or ""},
            )
        )
    except LLMConfigurationError as exc:
        yield _stream_event(
            ChatStreamEvent(
                event="error",
                data={
                    "message": str(exc),
                    "status": status.HTTP_503_SERVICE_UNAVAILABLE,
                    "request_id": request_id or "",
                },
            )
        )
    except Exception as exc:
        logger.exception("Chat stream failed")
        yield _stream_event(
            ChatStreamEvent(
                event="error",
                data={
                    "message": str(exc)
                    or "Unexpected server error while streaming response.",
                    "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "request_id": request_id or "",
                },
            )
        )

###############################################################################
@router.post(
    CHAT_TURN_ROUTE,
    response_model=ChatTurnResponse,
    status_code=status.HTTP_200_OK,
)
async def chat_turn(
    payload: ChatTurnRequest,
    runtime: ChatRuntime = Depends(get_chat_runtime),
) -> ChatTurnResponse:
    payload = _ensure_request_id(payload)
    try:
        return await runtime.agent_orchestrator.run_turn(payload)
    except LLMConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

###############################################################################
@router.post(
    CHAT_STREAM_ROUTE,
    status_code=status.HTTP_200_OK,
)
async def chat_stream(
    payload: ChatTurnRequest,
    runtime: ChatRuntime = Depends(get_chat_runtime),
) -> StreamingResponse:
    return StreamingResponse(
        _chat_event_stream(payload, runtime),
        media_type="application/x-ndjson",
    )

###############################################################################
@router.get(
    CHAT_MODELS_ROUTE,
    response_model=ModelLibraryResponse,
    status_code=status.HTTP_200_OK,
)
def get_models(runtime: ChatRuntime = Depends(get_chat_runtime)) -> ModelLibraryResponse:
    response = runtime.model_library_service.list_models(
        ollama_url=runtime.settings_service.get_ollama_url()
    )
    return ModelLibraryResponse.model_validate(response)

###############################################################################
@router.get(
    CHAT_SETTINGS_ROUTE,
    response_model=ModelSettingsResponse,
    status_code=status.HTTP_200_OK,
)
def get_settings(runtime: ChatRuntime = Depends(get_chat_runtime)) -> ModelSettingsResponse:
    return runtime.settings_service.get_settings()

###############################################################################
@router.put(
    CHAT_SETTINGS_ROUTE,
    response_model=ModelSettingsResponse,
    status_code=status.HTTP_200_OK,
)
def update_settings(
    payload: Annotated[
        ModelSettingsUpdateRequest, Body(default_factory=ModelSettingsUpdateRequest)
    ],
    runtime: ChatRuntime = Depends(get_chat_runtime),
) -> ModelSettingsResponse:
    return runtime.settings_service.update_settings(
        payload.model_dump(mode="python", exclude_none=True)
    )

###############################################################################
@router.post(
    CHAT_OLLAMA_REFRESH_ROUTE,
    response_model=OllamaRefreshResponse,
    status_code=status.HTTP_200_OK,
)
def refresh_ollama_models(runtime: ChatRuntime = Depends(get_chat_runtime)) -> OllamaRefreshResponse:
    return runtime.maintenance_service.refresh_ollama_models()

###############################################################################
@router.post(
    CHAT_OLLAMA_PULL_ROUTE,
    response_model=OllamaPullResponse,
    status_code=status.HTTP_200_OK,
)
def pull_ollama_model(
    payload: Annotated[OllamaPullRequest | None, Body()] = None,
    runtime: ChatRuntime = Depends(get_chat_runtime),
) -> OllamaPullResponse:
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="model is required"
        )
    try:
        return runtime.maintenance_service.pull_ollama_model(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc) or "Ollama pull failed",
        ) from exc

###############################################################################
@router.post(
    CHAT_VECTORS_REBUILD_ROUTE,
    response_model=VectorizationResponse,
    status_code=status.HTTP_200_OK,
)
def rebuild_vectors(runtime: ChatRuntime = Depends(get_chat_runtime)) -> VectorizationResponse:
    return runtime.maintenance_service.rebuild_vectors()

###############################################################################
@router.post(
    CHAT_VECTORS_SYNC_ROUTE,
    response_model=VectorizationResponse,
    status_code=status.HTTP_200_OK,
)
def sync_vectors(runtime: ChatRuntime = Depends(get_chat_runtime)) -> VectorizationResponse:
    return runtime.maintenance_service.sync_vectors()

###############################################################################
@router.get(
    CHAT_OLLAMA_HEALTH_ROUTE,
    response_model=OllamaHealthResponse,
    status_code=status.HTTP_200_OK,
)
def check_ollama_health(runtime: ChatRuntime = Depends(get_chat_runtime)) -> OllamaHealthResponse:
    return runtime.maintenance_service.get_ollama_health()
