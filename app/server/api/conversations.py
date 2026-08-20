from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status

from server.common.paths import (
    CONVERSATIONS_ROOT_ROUTE,
    CONVERSATIONS_ROUTER_PREFIX,
)
from server.contracts.runs import (
    ConversationCreateRequest,
    ConversationCreateResponse,
)
from server.services.agent_runs.lifecycle import RunLifecycleService

router = APIRouter(prefix=CONVERSATIONS_ROUTER_PREFIX, tags=["conversations"])

###############################################################################
def get_run_lifecycle_service(request: Request) -> RunLifecycleService:
    return request.app.state.run_lifecycle_service

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
