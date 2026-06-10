from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from server.common.paths import (
    CHAT_MODELS_ROUTE,
    CHAT_OLLAMA_HEALTH_ROUTE,
    CHAT_OLLAMA_PULL_ROUTE,
    CHAT_OLLAMA_REFRESH_ROUTE,
    CHAT_JOBS_ROUTE,
    CHAT_ROUTER_PREFIX,
    CHAT_SETTINGS_ROUTE,
    CHAT_STREAM_ROUTE,
    CHAT_TURN_ROUTE,
)
from server.domain.chat import (
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
)
from server.domain.jobs import BackgroundJobCreateResponse
from server.services.chat.composition import ChatRuntime
from server.services.jobs import BackgroundJobService
from server.services.chat.settings_service import ChatSettingsValidationError
from server.services.chat.streaming import ChatStreamingService
from server.services.llm.errors import LLMConfigurationError

router = APIRouter(prefix=CHAT_ROUTER_PREFIX, tags=["chat"])


def get_chat_runtime(request: Request) -> ChatRuntime:
    return request.app.state.chat_runtime


def get_job_service(request: Request) -> BackgroundJobService:
    return request.app.state.job_service


def get_chat_streaming_service(request: Request) -> ChatStreamingService:
    return request.app.state.chat_streaming_service


###############################################################################
def _stream_event(event: ChatStreamEvent) -> str:
    return json.dumps(event.model_dump(mode="json")) + "\n"


def _ensure_request_id(payload: ChatTurnRequest) -> ChatTurnRequest:
    if payload.request_id:
        return payload
    return payload.model_copy(update={"request_id": f"chat-{uuid4().hex[:12]}"})


async def _serialize_chat_event_stream(
    streaming_service: ChatStreamingService,
    payload: ChatTurnRequest,
) -> AsyncIterator[str]:
    payload = _ensure_request_id(payload)
    async for event in streaming_service.stream_turn(payload):
        yield _stream_event(event)


@router.post(
    CHAT_JOBS_ROUTE,
    response_model=BackgroundJobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_chat_job(
    payload: ChatTurnRequest,
    job_service: BackgroundJobService = Depends(get_job_service),
) -> BackgroundJobCreateResponse:
    payload = _ensure_request_id(payload)
    return job_service.create_chat_job(payload)


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


@router.post(
    CHAT_STREAM_ROUTE,
    status_code=status.HTTP_200_OK,
)
async def chat_stream(
    payload: ChatTurnRequest,
    streaming_service: ChatStreamingService = Depends(get_chat_streaming_service),
) -> StreamingResponse:
    return StreamingResponse(
        _serialize_chat_event_stream(streaming_service, payload),
        media_type="application/x-ndjson",
    )


@router.get(
    CHAT_MODELS_ROUTE,
    response_model=ModelLibraryResponse,
    status_code=status.HTTP_200_OK,
)
def get_models(
    runtime: ChatRuntime = Depends(get_chat_runtime),
) -> ModelLibraryResponse:
    response = runtime.model_library_service.list_models(
        ollama_url=runtime.settings_service.get_ollama_url()
    )
    return ModelLibraryResponse.model_validate(response)


@router.get(
    CHAT_SETTINGS_ROUTE,
    response_model=ModelSettingsResponse,
    status_code=status.HTTP_200_OK,
)
def get_settings(
    runtime: ChatRuntime = Depends(get_chat_runtime),
) -> ModelSettingsResponse:
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
    try:
        return runtime.settings_service.update_settings(payload)
    except ChatSettingsValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    CHAT_OLLAMA_REFRESH_ROUTE,
    response_model=OllamaRefreshResponse,
    status_code=status.HTTP_200_OK,
)
def refresh_ollama_models(
    runtime: ChatRuntime = Depends(get_chat_runtime),
) -> OllamaRefreshResponse:
    return runtime.maintenance_service.refresh_ollama_models()


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


@router.get(
    CHAT_OLLAMA_HEALTH_ROUTE,
    response_model=OllamaHealthResponse,
    status_code=status.HTTP_200_OK,
)
def check_ollama_health(
    runtime: ChatRuntime = Depends(get_chat_runtime),
) -> OllamaHealthResponse:
    return runtime.maintenance_service.get_ollama_health()
