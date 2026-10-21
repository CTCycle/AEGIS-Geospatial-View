from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from server.common.paths import (
    CHAT_ATTACHMENTS_ROUTE,
    CHAT_MODELS_ROUTE,
    CHAT_OLLAMA_HEALTH_ROUTE,
    CHAT_OLLAMA_PULL_ROUTE,
    CHAT_OLLAMA_REFRESH_ROUTE,
    CHAT_ROUTER_PREFIX,
    CHAT_SETTINGS_ROUTE,
    CHAT_TURN_ROUTE,
)
from server.contracts.chat import (
    AgentRunAcceptedResponse,
    ChatAttachmentCreateRequest,
    ChatAttachmentResponse,
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
from server.contracts.runs import AgentRunCreateRequest
from server.contracts.runs import AgentRunState
from server.services.chat.composition import ChatRuntime
from server.services.geospatial.render_capture import RenderCaptureStore
from server.domain.agent.trace import public_protocol_projection
from server.services.chat.model_library import DYNAMIC_CLOUD_PROVIDERS
from server.services.chat.settings_service import ChatSettingsValidationError
from server.services.agent_runs.lifecycle import RunLifecycleService
from server.services.agent_runs.exceptions import (
    RunAccessError,
    RunAttachmentError,
    RunConflictError,
    RunNotFoundError,
)
from server.services.llm.errors import (
    LLMConfigurationError,
    LLMProviderRequestError,
    safe_failure_detail,
)

router = APIRouter(prefix=CHAT_ROUTER_PREFIX, tags=["chat"])
LOGGER = logging.getLogger(__name__)

###############################################################################
def get_chat_runtime(request: Request) -> ChatRuntime:
    return request.app.state.chat_runtime

###############################################################################
def _build_run_request(payload: ChatTurnRequest) -> AgentRunCreateRequest:
    # Reject unusable input before any run is created; the
    # error detail omits the submitted value so an oversize message is not echoed.
    try:
        return AgentRunCreateRequest(
            message=payload.message,
            client_request_id=payload.request_id,
            timezone=payload.timezone,
            attachment_id=payload.attachment_id,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(
                include_url=False, include_context=False, include_input=False
            ),
        ) from exc

###############################################################################
@router.post(
    CHAT_TURN_ROUTE,
    response_model=ChatTurnResponse | AgentRunAcceptedResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_202_ACCEPTED: {
            "model": AgentRunAcceptedResponse,
            "description": "The run was accepted and is still executing.",
        },
        status.HTTP_409_CONFLICT: {
            "description": "The request conflicts with an active run.",
        },
    },
)
async def chat_turn(
    payload: ChatTurnRequest,
    request: Request,
    runtime: ChatRuntime = Depends(get_chat_runtime),
) -> ChatTurnResponse | AgentRunAcceptedResponse | JSONResponse:
    run_request = _build_run_request(payload)
    try:
        if (
            runtime.conversation_repository.get_conversation(payload.conversation_id)
            is None
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found.",
            )
        lifecycle_service = getattr(request.app.state, "run_lifecycle_service", None)
        if not isinstance(lifecycle_service, RunLifecycleService):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The persisted agent-run lifecycle is unavailable.",
            )
        response, result, _created = await lifecycle_service.run_turn(
            payload.conversation_id,
            run_request,
            owner_user_id=(
                str(getattr(request.state, "user_id")).strip()
                if getattr(request.state, "user_id", None) is not None
                else None
            ),
        )
        if response is not None:
            return response.model_copy(
                update={
                    "execution_trace": public_protocol_projection(
                        response.execution_trace
                    )
                }
            )
        snapshot = lifecycle_service.run_repository.get_run(result.run_id)
        if snapshot is not None and snapshot.error_message:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=snapshot.error_message,
            )
        if snapshot is not None and snapshot.state in {
            AgentRunState.PENDING,
            AgentRunState.RUNNING,
            AgentRunState.UPDATING,
            AgentRunState.AWAITING_RENDER,
        }:
            accepted = AgentRunAcceptedResponse(
                conversation_id=snapshot.conversation_id,
                run_id=snapshot.run_id,
                run_version=snapshot.active_run_version,
                state=snapshot.state,
                presentation_status=snapshot.presentation_status,
                status_url=(
                    f"/api/conversations/{snapshot.conversation_id}/runs/"
                    f"{snapshot.run_id}"
                ),
                realtime_url=(
                    f"/api/conversations/{snapshot.conversation_id}/realtime"
                ),
            )
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content=accepted.model_dump(mode="json"),
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The agent run ended without a terminal response.",
        )
    except (RunNotFoundError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc) or "Conversation not found.",
        ) from exc
    except RunAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except RunConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except RunAttachmentError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

###############################################################################
@router.post(
    CHAT_ATTACHMENTS_ROUTE,
    response_model=ChatAttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_chat_attachment(
    payload: ChatAttachmentCreateRequest,
    request: Request,
    runtime: ChatRuntime = Depends(get_chat_runtime),
) -> ChatAttachmentResponse:
    """Hold one user image for the next run start that references it."""
    if runtime.conversation_repository.get_conversation(payload.conversation_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )
    store: RenderCaptureStore = request.app.state.render_capture_store
    try:
        attachment_id = store.save_attachment(
            conversation_id=payload.conversation_id,
            mime_type=payload.mime_type,
            image_base64=payload.image_base64,
            width=payload.width,
            height=payload.height,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return ChatAttachmentResponse(
        attachment_id=attachment_id,
        expires_in_seconds=int(store.ttl_seconds),
    )

###############################################################################
@router.get(
    CHAT_MODELS_ROUTE,
    response_model=ModelLibraryResponse,
    status_code=status.HTTP_200_OK,
)
def get_models(
    provider: str | None = Query(default=None),
    runtime: ChatRuntime = Depends(get_chat_runtime),
) -> ModelLibraryResponse:
    requested_provider = provider if isinstance(provider, str) else None
    if (
        requested_provider is not None
        and requested_provider not in DYNAMIC_CLOUD_PROVIDERS
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported dynamic cloud provider '{requested_provider}'.",
        )
    cloud_provider = requested_provider
    try:
        response = runtime.model_library_service.list_models(
            ollama_url=runtime.settings_service.get_ollama_url(),
            cloud_provider=cloud_provider,
        )
        return ModelLibraryResponse.model_validate(response)
    except LLMConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        LOGGER.warning(
            "Failed to load cloud model catalog provider=%s error=%s",
            cloud_provider or "*",
            safe_failure_detail(exc, "Cloud model catalog unavailable."),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"Could not load {cloud_provider} models."
                if cloud_provider is not None
                else "Could not load cloud models."
            ),
        ) from exc

###############################################################################
@router.get(
    CHAT_SETTINGS_ROUTE,
    response_model=ModelSettingsResponse,
    status_code=status.HTTP_200_OK,
)
def get_settings(
    runtime: ChatRuntime = Depends(get_chat_runtime),
) -> ModelSettingsResponse:
    try:
        return runtime.settings_service.get_settings()
    except ChatSettingsValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

###############################################################################
@router.patch(
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

###############################################################################
@router.post(
    CHAT_OLLAMA_REFRESH_ROUTE,
    response_model=OllamaRefreshResponse,
    status_code=status.HTTP_200_OK,
)
def refresh_ollama_models(
    runtime: ChatRuntime = Depends(get_chat_runtime),
) -> OllamaRefreshResponse:
    try:
        return runtime.maintenance_service.refresh_ollama_models()
    except LLMProviderRequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

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
        LOGGER.warning(
            "Ollama model pull failed error=%s",
            safe_failure_detail(exc, "Ollama pull failed."),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Ollama pull failed.",
        ) from exc

###############################################################################
@router.get(
    CHAT_OLLAMA_HEALTH_ROUTE,
    response_model=OllamaHealthResponse,
    status_code=status.HTTP_200_OK,
)
def check_ollama_health(
    runtime: ChatRuntime = Depends(get_chat_runtime),
) -> OllamaHealthResponse:
    return runtime.maintenance_service.get_ollama_health()
