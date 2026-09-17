from __future__ import annotations

import asyncio

from server.contracts.runs import (
    AgentRunCancelResponse,
    AgentRunCreateRequest,
    AgentRunCreateResult,
    AgentRunState,
    ConversationCreateResponse,
)
from server.domain.realtime import RealtimeRenderAckPayload
from server.services.agent_runs.render_completion import (
    RenderAcknowledgementError,
    RenderAcknowledgementResult,
)
from server.contracts.chat import ChatTurnResponse
from server.contracts.events import RunEventType
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
        self.render_completion_service = getattr(
            run_orchestrator, "render_completion_service", None
        )
        self._tasks: set[asyncio.Task[ChatTurnResponse | None]] = set()
        self._tasks_by_run: dict[str, asyncio.Task[ChatTurnResponse | None]] = {}

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
        result, _created = await self.create_run_with_status(conversation_id, payload)
        return result

    # -------------------------------------------------------------------------
    async def create_run_with_status(
        self,
        conversation_id: str,
        payload: AgentRunCreateRequest,
        *,
        schedule: bool = True,
        owner_user_id: str | None = None,
    ) -> tuple[AgentRunCreateResult, bool]:
        try:
            self.conversation_repository.verify_conversation_access(
                conversation_id, owner_user_id
            )
        except ValueError as exc:
            raise RunNotFoundError("Conversation not found.") from exc
        except PermissionError as exc:
            raise RunAccessError("Conversation access denied.") from exc
        aggregate = self.aggregation_service.build_aggregated_request(
            payload.message, []
        )
        try:
            run, created = self.run_repository.create_or_get_run(
                conversation_id,
                payload.message,
                aggregate,
                client_request_id=payload.client_request_id,
                request_timezone=payload.timezone,
            )
        except ValueError as exc:
            message = str(exc)
            if "active run" in message:
                raise RunConflictError(message) from exc
            raise RunNotFoundError(message) from exc
        except PermissionError as exc:
            raise RunAccessError(str(exc)) from exc
        if created and schedule:
            self._schedule_run(run.run_id)
        return AgentRunCreateResult(
            conversation_id=conversation_id,
            run_id=run.run_id,
            run_version=run.active_run_version,
            state=run.state,
        ), created

    # -------------------------------------------------------------------------
    async def execute_run(self, run_id: str) -> ChatTurnResponse | None:
        """Execute or observe one persisted run through the canonical worker.

        Realtime connections schedule runs through ``create_run_with_status``;
        synchronous HTTP and NDJSON transports call this method with
        ``schedule=False``.  Both paths therefore enter the exact same
        persisted ``AgentRunOrchestrator`` boundary and never invoke the
        native model directly from a transport.
        """

        existing = self._tasks_by_run.get(run_id)
        if existing is not None and not existing.done():
            return await existing
        return await self.run_orchestrator.execute_run(run_id)

    # -------------------------------------------------------------------------
    async def acknowledge_render(
        self,
        conversation_id: str,
        payload: RealtimeRenderAckPayload,
    ) -> RenderAcknowledgementResult:
        """Apply browser evidence and resume the same native run when needed."""

        service = self.render_completion_service
        if service is None:
            raise RenderAcknowledgementError("Render acknowledgment is unavailable.")
        result = await service.acknowledge(
            conversation_id=conversation_id,
            payload=payload,
        )
        if result.resume_required:
            self._schedule_run_if_idle(result.run_id)
        return result

    # -------------------------------------------------------------------------
    async def run_turn(
        self,
        conversation_id: str,
        payload: AgentRunCreateRequest,
        *,
        owner_user_id: str | None = None,
    ) -> tuple[ChatTurnResponse | None, AgentRunCreateResult, bool]:
        """Create/observe one run and return its canonical response if ready."""

        result, created = await self.create_run_with_status(
            conversation_id,
            payload,
            schedule=False,
            owner_user_id=owner_user_id,
        )
        response = await self.execute_run(result.run_id)
        if response is None:
            response = self.read_completed_response(
                conversation_id,
                result.run_id,
            )
        return response, result, created

    # -------------------------------------------------------------------------
    def read_completed_response(
        self,
        conversation_id: str,
        run_id: str,
    ) -> ChatTurnResponse | None:
        """Hydrate a terminal response from the durable user event envelope."""

        snapshot = self.run_repository.get_run(run_id)
        if snapshot is None or snapshot.conversation_id != conversation_id:
            return None
        for event in reversed(self.event_publisher.replay(run_id)):
            if event.type.value not in {"completed", "clarification_needed"}:
                continue
            payload = dict(event.payload)
            if "assistant_message" not in payload and "content" in payload:
                payload["assistant_message"] = payload.get("content")
            payload.pop("content", None)
            payload.pop("content", None)
            try:
                return ChatTurnResponse.model_validate(payload)
            except (TypeError, ValueError):
                continue
        return None

    # -------------------------------------------------------------------------
    def resume_active_runs(self) -> int:
        """Requeue non-terminal runs after application startup."""

        scheduled = 0
        for snapshot in self.run_repository.list_resumable_runs():
            if snapshot.run_id in self._tasks_by_run:
                continue
            self._schedule_run(snapshot.run_id)
            scheduled += 1
        return scheduled

    # -------------------------------------------------------------------------
    def _schedule_run(self, run_id: str) -> None:
        task = asyncio.create_task(self.run_orchestrator.execute_run(run_id))
        self._tasks.add(task)
        self._tasks_by_run[run_id] = task

        def discard_task(
            completed: asyncio.Task[ChatTurnResponse | None],
        ) -> None:
            self._tasks.discard(completed)
            if self._tasks_by_run.get(run_id) is completed:
                self._tasks_by_run.pop(run_id, None)

        task.add_done_callback(discard_task)

    # -------------------------------------------------------------------------
    def _schedule_run_if_idle(self, run_id: str) -> None:
        existing = self._tasks_by_run.get(run_id)
        if existing is not None and not existing.done():
            # The worker that prepared the candidate can still be unwinding
            # its ``awaiting_render`` return when the browser acknowledges it.
            # Queue a second CAS-protected worker instead of dropping the
            # resume: the first worker is already past model execution and
            # ``mark_started_if_current`` ensures only one continuation wins.
            self._schedule_run(run_id)
            return
        self._schedule_run(run_id)

    # -------------------------------------------------------------------------
    async def shutdown(self) -> None:
        tasks = set(self._tasks)
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        self._tasks_by_run.clear()

    # -------------------------------------------------------------------------
    async def cancel_run(
        self, conversation_id: str, run_id: str
    ) -> AgentRunCancelResponse:
        response, _transitioned = await self.cancel_run_with_status(
            conversation_id, run_id
        )
        return response

    # -------------------------------------------------------------------------
    async def cancel_run_with_status(
        self, conversation_id: str, run_id: str
    ) -> tuple[AgentRunCancelResponse, bool]:
        snapshot = self.run_repository.get_run(run_id)
        if snapshot is None or snapshot.conversation_id != conversation_id:
            raise RunNotFoundError("Run not found.")
        cancelled, transitioned = self.run_repository.request_cancel_once(run_id)
        task = self._tasks_by_run.get(run_id)
        if task is not None and not task.done():
            task.cancel()
        if transitioned:
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
        ), transitioned
