from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from server.common.paths import (
    CONVERSATION_RUN_STATUS_ROUTE,
    CONVERSATIONS_ROOT_ROUTE,
    CONVERSATIONS_ROUTER_PREFIX,
)
from server.contracts.runs import (
    ConversationListResponse,
    ConversationSummary,
    ConversationCreateRequest,
    ConversationCreateResponse,
    ConversationSnapshotResponse,
    AgentRunSnapshot,
    RunTraceEntry,
    RunTraceResponse,
)
from server.repositories.agent_runs import AgentRunRepository
from server.repositories.conversations import ConversationRepository
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
def get_conversation_repository(request: Request) -> ConversationRepository:
    return request.app.state.conversation_repository


###############################################################################
def get_run_repository(request: Request) -> AgentRunRepository:
    return request.app.state.run_repository


###############################################################################
def _owner_user_id(request: Request) -> str | None:
    """Read the authenticated owner identity when an auth middleware provides it."""

    value = getattr(request.state, "user_id", None)
    return str(value).strip() if value is not None and str(value).strip() else None

###############################################################################
@router.post(
    CONVERSATIONS_ROOT_ROUTE,
    response_model=ConversationCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    payload: ConversationCreateRequest,
    request: Request,
    lifecycle_service: RunLifecycleService = Depends(get_run_lifecycle_service),
) -> ConversationCreateResponse:
    return lifecycle_service.create_conversation(
        title=payload.title,
        owner_user_id=_owner_user_id(request),
    )


###############################################################################
@router.get(
    CONVERSATIONS_ROOT_ROUTE,
    response_model=ConversationListResponse,
    status_code=status.HTTP_200_OK,
)
def list_conversations(
    request: Request,
    query: str | None = Query(default=None, max_length=300),
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = Query(default=None, max_length=500),
    conversation_repository: ConversationRepository = Depends(
        get_conversation_repository
    ),
    run_repository: AgentRunRepository = Depends(get_run_repository),
) -> ConversationListResponse:
    try:
        page: dict[str, Any] = conversation_repository.list_conversation_page(
            query=query,
            cursor=cursor,
            limit=limit,
            owner_user_id=_owner_user_id(request),
        )
        summaries: list[ConversationSummary] = []
        for item in page.get("conversations", []):
            if not isinstance(item, dict):
                continue
            item_payload = cast(dict[str, Any], item)
            recent_runs = run_repository.list_run_summaries(
                str(item_payload.get("conversation_id") or ""),
                limit=1,
            )
            latest_raw = recent_runs.get("runs", [])
            latest = (
                latest_raw[0]
                if latest_raw and isinstance(latest_raw[0], dict)
                else None
            )
            summary_payload: dict[str, Any] = {
                key: item_payload.get(key)
                for key in (
                    "conversation_id",
                    "title",
                    "context_revision",
                    "message_count",
                    "last_message_preview",
                    "created_at",
                    "updated_at",
                )
            }
            summary_payload["latest_run"] = latest
            summaries.append(ConversationSummary.model_validate(summary_payload))
        return ConversationListResponse(
            conversations=summaries,
            next_cursor=page.get("next_cursor"),
            has_more=bool(page.get("has_more", False)),
            total=int(page.get("total", len(summaries))),
            pagination=cast(
                dict[str, Any],
                page.get("pagination")
                if isinstance(page.get("pagination"), dict)
                else {},
            ),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

###############################################################################
@router.get(
    "/{conversation_id}",
    response_model=ConversationSnapshotResponse,
    status_code=status.HTTP_200_OK,
)
def get_conversation_snapshot(
    conversation_id: str,
    request: Request,
    snapshot_service: ConversationSnapshotService = Depends(
        get_conversation_snapshot_service
    ),
) -> ConversationSnapshotResponse:
    try:
        # The snapshot service keeps the repository access check as its
        # canonical guard.  Auth middleware can additionally place the owner
        # identity on request.state; anonymous local mode remains unowned-only.
        return snapshot_service.get_snapshot(
            conversation_id,
            owner_user_id=_owner_user_id(request),
        )
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


###############################################################################
@router.get(
    CONVERSATION_RUN_STATUS_ROUTE,
    response_model=AgentRunSnapshot,
    status_code=status.HTTP_200_OK,
)
def get_run_status(
    conversation_id: str,
    run_id: str,
    request: Request,
    lifecycle_service: RunLifecycleService = Depends(get_run_lifecycle_service),
    conversation_repository: ConversationRepository = Depends(
        get_conversation_repository
    ),
    run_repository: AgentRunRepository = Depends(get_run_repository),
) -> AgentRunSnapshot:
    """Return active or terminal run state for 202 polling clients."""

    try:
        conversation_repository.verify_conversation_access(
            conversation_id,
            _owner_user_id(request),
        )
        snapshot = run_repository.get_run(run_id)
        if snapshot is None or snapshot.conversation_id != conversation_id:
            raise ValueError("Run not found.")
        response = lifecycle_service.read_completed_response(conversation_id, run_id)
        if response is not None:
            snapshot = snapshot.model_copy(
                update={"response": response.model_dump(mode="json")}
            )
        return snapshot
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Conversation access denied.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run not found.",
        ) from exc


###############################################################################
@router.get(
    "/{conversation_id}/runs/{run_id}/trace",
    response_model=RunTraceResponse,
    status_code=status.HTTP_200_OK,
)
def get_run_trace(
    conversation_id: str,
    run_id: str,
    request: Request,
    run_version: int | None = Query(default=None, ge=1),
    after_sequence: int | None = Query(default=None, ge=0),
    cursor: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=100, ge=1, le=200),
    include_internal: bool = Query(default=True),
    conversation_repository: ConversationRepository = Depends(
        get_conversation_repository
    ),
    run_repository: AgentRunRepository = Depends(get_run_repository),
) -> RunTraceResponse:
    try:
        conversation_repository.verify_conversation_access(
            conversation_id,
            _owner_user_id(request),
        )
        page = run_repository.read_trace(
            conversation_id,
            run_id,
            run_version=run_version,
            after_sequence=after_sequence,
            cursor=cursor,
            limit=limit,
            include_internal=include_internal,
        )
        entries = [
            RunTraceEntry.model_validate(item)
            for item in page.get("events", [])
            if isinstance(item, dict)
        ]
        return RunTraceResponse(
            conversation_id=conversation_id,
            run_id=run_id,
            run_version=run_version,
            events=entries,
            next_cursor=page.get("next_cursor"),
            has_more=bool(page.get("has_more", False)),
            total=int(page.get("total", len(entries))),
            pagination=cast(
                dict[str, Any],
                page.get("pagination")
                if isinstance(page.get("pagination"), dict)
                else {},
            ),
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Conversation access denied.",
        ) from exc
    except ValueError as exc:
        detail = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in detail.casefold()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=detail) from exc
