from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from server.common.paths import (
    CONVERSATIONS_ROOT_ROUTE,
    CONVERSATIONS_ROUTER_PREFIX,
)
from server.contracts.runs import (
    ConversationCreateRequest,
    ConversationCreateResponse,
    ConversationSnapshotResponse,
)
from server.services.agent_runs.lifecycle import RunLifecycleService
from server.services.chat.conversation_snapshot import (
    ConversationSnapshotContractError,
    ConversationSnapshotService,
)

router = APIRouter(prefix=CONVERSATIONS_ROUTER_PREFIX, tags=["conversations"])


###############################################################################
def get_run_lifecycle_service(request: Request) -> RunLifecycleService:
    return request.app.state.run_lifecycle_service


###############################################################################
def get_conversation_snapshot_service(
    request: Request,
) -> ConversationSnapshotService:
    return request.app.state.conversation_snapshot_service


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
@router.get(
    "/{conversation_id}",
    response_model=ConversationSnapshotResponse,
    status_code=status.HTTP_200_OK,
)
def get_conversation_snapshot(
    conversation_id: str,
    snapshot_service: ConversationSnapshotService = Depends(
        get_conversation_snapshot_service
    ),
) -> ConversationSnapshotResponse:
    try:
        return snapshot_service.get_snapshot(conversation_id)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Conversation access denied.",
        ) from exc
    except ConversationSnapshotContractError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        ) from exc
