from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated, Any

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
from AEGIS.server.services.chat.composition import ChatRuntime
from AEGIS.server.services.llm.ollama import OllamaProvider
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


###############################################################################
async def _chat_event_stream(
    payload: ChatTurnRequest,
    runtime: ChatRuntime,
) -> AsyncIterator[str]:
    yield _stream_event(ChatStreamEvent(event="status", data={"message": "received"}))
    try:
        result = await runtime.agent_orchestrator.run_turn(payload)
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
                    "assistant_message": result.assistant_message,
                    "structured_intent": result.structured_intent,
                    "extracted_state": result.extracted_state,
                    "map_session": result.map_session,
                    "follow_up_required": result.follow_up_required,
                    "fallback_mode": result.fallback_mode,
                },
            )
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
        yield _stream_event(
            ChatStreamEvent(
                event="error",
                data={"message": detail, "status": exc.status_code},
            )
        )
    except ValueError as exc:
        yield _stream_event(
            ChatStreamEvent(
                event="error",
                data={
                    "message": str(exc),
                    "status": status.HTTP_503_SERVICE_UNAVAILABLE,
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
                },
            )
        )


@router.post(
    CHAT_TURN_ROUTE,
    response_model=ChatTurnResponse,
    status_code=status.HTTP_200_OK,
)
async def chat_turn(
    payload: ChatTurnRequest,
    runtime: ChatRuntime = Depends(get_chat_runtime),
) -> ChatTurnResponse:
    try:
        return await runtime.agent_orchestrator.run_turn(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc


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


@router.get(
    CHAT_SETTINGS_ROUTE,
    response_model=ModelSettingsResponse,
    status_code=status.HTTP_200_OK,
)
def get_settings(runtime: ChatRuntime = Depends(get_chat_runtime)) -> ModelSettingsResponse:
    return runtime.settings_service.get_settings()


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


@router.post(
    CHAT_OLLAMA_REFRESH_ROUTE,
    response_model=OllamaRefreshResponse,
    status_code=status.HTTP_200_OK,
)
def refresh_ollama_models(runtime: ChatRuntime = Depends(get_chat_runtime)) -> OllamaRefreshResponse:
    provider = OllamaProvider(base_url=runtime.settings_service.get_ollama_url())
    library_models = provider.list_library_models()
    local_models = provider.list_models()
    return OllamaRefreshResponse(
        status="ok",
        library_models=[model.name for model in library_models],
        local_models=[model.name for model in local_models],
    )


@router.post(
    CHAT_OLLAMA_PULL_ROUTE,
    response_model=OllamaPullResponse,
    status_code=status.HTTP_200_OK,
)
def pull_ollama_model(
    payload: Annotated[OllamaPullRequest | None, Body()] = None,
    runtime: ChatRuntime = Depends(get_chat_runtime),
) -> OllamaPullResponse:
    model_name = payload.model.strip() if payload is not None else ""
    if not model_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="model is required"
        )
    provider = OllamaProvider(base_url=runtime.settings_service.get_ollama_url())
    try:
        return OllamaPullResponse.model_validate(provider.pull_model(model=model_name))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc) or "Ollama pull failed",
        ) from exc


@router.post(
    CHAT_VECTORS_REBUILD_ROUTE,
    response_model=VectorizationResponse,
    status_code=status.HTTP_200_OK,
)
def rebuild_vectors(runtime: ChatRuntime = Depends(get_chat_runtime)) -> VectorizationResponse:
    result = runtime.vector_indexer.rebuild()
    return VectorizationResponse.model_validate(result)


@router.post(
    CHAT_VECTORS_SYNC_ROUTE,
    response_model=VectorizationResponse,
    status_code=status.HTTP_200_OK,
)
def sync_vectors(runtime: ChatRuntime = Depends(get_chat_runtime)) -> VectorizationResponse:
    result = runtime.vector_indexer.sync()
    return VectorizationResponse.model_validate(result)


@router.get(
    CHAT_OLLAMA_HEALTH_ROUTE,
    response_model=OllamaHealthResponse,
    status_code=status.HTTP_200_OK,
)
def check_ollama_health(runtime: ChatRuntime = Depends(get_chat_runtime)) -> OllamaHealthResponse:
    provider = OllamaProvider(base_url=runtime.settings_service.get_ollama_url())
    return OllamaHealthResponse.model_validate(provider.health_check())