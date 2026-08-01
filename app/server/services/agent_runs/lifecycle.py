from __future__ import annotations

import asyncio

from server.domain.agent_runs import (
    AgentRunCancelResponse,
    AgentRunCreateRequest,
    AgentRunCreateResult,
    AgentRunState,
    ConversationCreateResponse,
    TERMINAL_RUN_STATES,
)
from server.domain.run_events import RunEventType
from server.repositories.agent_runs import AgentRunRepository
from server.repositories.conversations import ConversationRepository
from server.services.agent_runs.aggregation import AggregatedRequestService
from server.services.agent_runs.events import RunEventPublisher
from server.services.agent_runs.exceptions import (
    RunAccessError,
    RunConflictError,
    RunNotFoundError,
)
from server.services.agent_runs.orchestrator import AgentRunOrchestrator

###############################################################################
class RunLifecycleService:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        conversation_repository: ConversationRepository,
        run_repository: AgentRunRepository,
        aggregation_service: AggregatedRequestService,
        event_publisher: RunEventPublisher,
        run_orchestrator: AgentRunOrchestrator,
    ) -> None:
        self.conversation_repository = conversation_repository
        self.run_repository = run_repository
        self.aggregation_service = aggregation_service
        self.event_publisher = event_publisher
        self.run_orchestrator = run_orchestrator
        self._tasks: set[asyncio.Task[None]] = set()

    # -------------------------------------------------------------------------
    def create_conversation(
        self,
        *,
        title: str | None = None,
        owner_user_id: str | None = None,
    ) -> ConversationCreateResponse:
        record = self.conversation_repository.create_conversation(title, owner_user_id)
        return ConversationCreateResponse(conversation_id=record.id, title=record.title)

    # -------------------------------------------------------------------------
    async def create_run(
        self,
        conversation_id: str,
        payload: AgentRunCreateRequest,
    ) -> AgentRunCreateResult:
        try:
            self.conversation_repository.verify_conversation_access(conversation_id, None)
        except ValueError as exc:
            raise RunNotFoundError("Conversation not found.") from exc
        except PermissionError as exc:
            raise RunAccessError("Conversation access denied.") from exc
        active = self.run_repository.get_active_run_for_conversation(conversation_id)
        if active is not None and active.state not in TERMINAL_RUN_STATES:
            raise RunConflictError("Conversation already has an active run.")
        aggregate = self.aggregation_service.build_aggregated_request(payload.message, [])
        try:
            run = self.run_repository.create_run(conversation_id, payload.message, aggregate)
        except ValueError as exc:
            message = str(exc)
            if "active run" in message:
                raise RunConflictError(message) from exc
            raise RunNotFoundError(message) from exc
        except PermissionError as exc:
            raise RunAccessError(str(exc)) from exc
        task = asyncio.create_task(self.run_orchestrator.execute_run(run.run_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return AgentRunCreateResult(
            conversation_id=conversation_id,
            run_id=run.run_id,
            run_version=run.active_run_version,
            state=run.state,
        )

    # -------------------------------------------------------------------------
    async def shutdown(self) -> None:
        tasks = set(self._tasks)
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    # -------------------------------------------------------------------------
    async def cancel_run(self, conversation_id: str, run_id: str) -> AgentRunCancelResponse:
        snapshot = self.run_repository.get_run(run_id)
        if snapshot is None or snapshot.conversation_id != conversation_id:
            raise RunNotFoundError("Run not found.")
        cancelled = self.run_repository.request_cancel(run_id)
        await self.event_publisher.publish(
            conversation_id=conversation_id,
            run_id=run_id,
            run_version=cancelled.active_run_version,
            type=RunEventType.CANCELLED,
            payload={"state": AgentRunState.CANCELLED.value},
        )
        return AgentRunCancelResponse(
            conversation_id=conversation_id,
            run_id=run_id,
            state=cancelled.state,
            cancel_requested_at=cancelled.cancel_requested_at,
        )
