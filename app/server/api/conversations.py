from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query, Request, status
from fastapi.responses import StreamingResponse

from server.common.paths import (
    FASTAPI_API_PREFIX,
    CONVERSATION_RUN_CANCEL_ROUTE,
    CONVERSATION_RUN_EVENTS_ROUTE,
    CONVERSATION_RUN_STEERING_ROUTE,
    CONVERSATION_RUNS_ROUTE,
    CONVERSATIONS_ROOT_ROUTE,
    CONVERSATIONS_ROUTER_PREFIX,
)
from server.domain.agent_runs import (
    AgentRunCancelRequest,
    AgentRunCancelResponse,
    AgentRunCreateRequest,
    AgentRunCreateResponse,
    ConversationCreateRequest,
    ConversationCreateResponse,
)
from server.domain.steering import SteeringMessageRequest, SteeringMessageResponse
from server.services.agent_runs.exceptions import RunServiceError
from server.api.run_errors import raise_run_http_error
from server.services.agent_runs.lifecycle import RunLifecycleService
from server.services.agent_runs.steering import RunSteeringService
from server.services.agent_runs.streaming import RunEventStreamService

router = APIRouter(prefix=CONVERSATIONS_ROUTER_PREFIX, tags=["conversations"])

###############################################################################
def get_run_lifecycle_service(request: Request) -> RunLifecycleService:
    return request.app.state.run_lifecycle_service

###############################################################################
def get_run_steering_service(request: Request) -> RunSteeringService:
    return request.app.state.run_steering_service

###############################################################################
def get_run_event_stream_service(request: Request) -> RunEventStreamService:
    return request.app.state.run_event_stream_service

###############################################################################
def _run_stream_url(conversation_id: str, run_id: str) -> str:
    return FASTAPI_API_PREFIX + CONVERSATIONS_ROUTER_PREFIX + CONVERSATION_RUN_EVENTS_ROUTE.format(
        conversation_id=conversation_id,
        run_id=run_id,
    )

###############################################################################
@router.post(
    CONVERSATIONS_ROOT_ROUTE,
    response_model=ConversationCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    payload: ConversationCreateRequest,
    lifecycle_service: RunLifecycleService = Depends(get_run_lifecycle_service),
) -> ConversationCreateResponse:
    return lifecycle_service.create_conversation(title=payload.title)

###############################################################################
@router.post(
    CONVERSATION_RUNS_ROUTE,
    response_model=AgentRunCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_agent_run(
    conversation_id: str,
    payload: AgentRunCreateRequest,
    lifecycle_service: RunLifecycleService = Depends(get_run_lifecycle_service),
) -> AgentRunCreateResponse:
    try:
        result = await lifecycle_service.create_run(conversation_id, payload)
        return AgentRunCreateResponse(
            **result.model_dump(),
            stream_url=_run_stream_url(result.conversation_id, result.run_id),
        )
    except RunServiceError as exc:
        raise_run_http_error(exc)

###############################################################################
@router.get(
    CONVERSATION_RUN_EVENTS_ROUTE,
    status_code=status.HTTP_200_OK,
)
async def stream_agent_run_events(
    conversation_id: str,
    run_id: str,
    after_event_id: str | None = Query(default=None),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    stream_service: RunEventStreamService = Depends(get_run_event_stream_service),
) -> StreamingResponse:
    try:
        stream_service.verify_run_access(conversation_id, run_id)
    except RunServiceError as exc:
        raise_run_http_error(exc)
    return StreamingResponse(
        stream_service.stream_sse(
            run_id,
            conversation_id=conversation_id,
            after_event_id=after_event_id or last_event_id,
        ),
        media_type="text/event-stream",
    )

###############################################################################
@router.post(
    CONVERSATION_RUN_STEERING_ROUTE,
    response_model=SteeringMessageResponse,
    status_code=status.HTTP_200_OK,
)
async def steer_agent_run(
    conversation_id: str,
    run_id: str,
    payload: SteeringMessageRequest,
    steering_service: RunSteeringService = Depends(get_run_steering_service),
) -> SteeringMessageResponse:
    try:
        return await steering_service.steer(conversation_id, run_id, payload)
    except RunServiceError as exc:
        raise_run_http_error(exc)

###############################################################################
@router.post(
    CONVERSATION_RUN_CANCEL_ROUTE,
    response_model=AgentRunCancelResponse,
    status_code=status.HTTP_200_OK,
)
async def cancel_agent_run(
    conversation_id: str,
    run_id: str,
    payload: AgentRunCancelRequest | None = None,
    lifecycle_service: RunLifecycleService = Depends(get_run_lifecycle_service),
) -> AgentRunCancelResponse:
    del payload
    try:
        return await lifecycle_service.cancel_run(conversation_id, run_id)
    except RunServiceError as exc:
        raise_run_http_error(exc)
