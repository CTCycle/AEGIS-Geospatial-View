from __future__ import annotations

from server.domain.chat import ChatTurnRequest, ChatTurnResponse
from server.domain.run_events import RUN_PROGRESS_LABELS, RunEventType, RunProgressStage, RunEventVisibility
from server.repositories.agent_runs import AgentRunRepository
from server.repositories.conversation_context import ConversationContextRepository
from server.services.agent.orchestrator import AgentOrchestrator
from server.services.agent_runs.events import RunEventPublisher

###############################################################################
class AgentRunOrchestrator:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        agent_orchestrator: AgentOrchestrator,
        run_repository: AgentRunRepository,
        event_publisher: RunEventPublisher,
        conversation_context_repository: ConversationContextRepository,
    ) -> None:
        self.agent_orchestrator = agent_orchestrator
        self.run_repository = run_repository
        self.event_publisher = event_publisher
        self.conversation_context_repository = conversation_context_repository

    # -------------------------------------------------------------------------
    async def execute_run(self, run_id: str) -> None:
        snapshot = self.run_repository.get_run(run_id)
        if snapshot is None:
            return
        if snapshot.cancel_requested_at is not None:
            await self._publish_cancelled(snapshot)
            return
        snapshot = self.run_repository.mark_started(run_id)
        await self._publish_progress(snapshot, RunProgressStage.UNDERSTANDING_REQUEST)
        try:
            chat_session_id = self.conversation_context_repository.resolve_chat_session_id(
                snapshot.conversation_id
            )
            response = await self.agent_orchestrator.run_turn(
                ChatTurnRequest(
                    session_id=chat_session_id,
                    message=snapshot.aggregated_request,
                    request_id=run_id,
                    title=snapshot.original_request[:120],
                    conversation_id=snapshot.conversation_id,
                )
            )
        except Exception as exc:
            latest = self.run_repository.get_run(run_id) or snapshot
            if latest.cancel_requested_at is not None:
                await self._publish_cancelled(latest)
                return
            self.run_repository.mark_failed(run_id, "agent_execution_failed", str(exc))
            await self.event_publisher.publish(
                conversation_id=latest.conversation_id,
                run_id=latest.run_id,
                run_version=latest.active_run_version,
                type=RunEventType.ERROR,
                payload={"code": "agent_execution_failed", "message": "Failed"},
            )
            return

        latest = self.run_repository.get_run(run_id) or snapshot
        if latest.cancel_requested_at is not None:
            await self._publish_cancelled(latest)
            return
        if latest.active_run_version != snapshot.active_run_version:
            await self.event_publisher.publish(
                conversation_id=latest.conversation_id,
                run_id=latest.run_id,
                run_version=latest.active_run_version,
                type=RunEventType.ERROR,
                visibility=RunEventVisibility.INTERNAL,
                payload={
                    "code": "stale_result_discarded",
                    "message": "Discarded stale agent result after steering update.",
                    "observed_version": snapshot.active_run_version,
                    "current_version": latest.active_run_version,
                },
            )
            await self.execute_run(run_id)
            return
        await self._publish_response(latest, response)
        if response.operation is not None and response.operation.kind == "clarification":
            clarified = self.run_repository.mark_completed(run_id)
            await self._publish_progress(
                clarified,
                RunProgressStage.WAITING_FOR_CLARIFICATION,
            )
            await self.event_publisher.publish(
                conversation_id=clarified.conversation_id,
                run_id=clarified.run_id,
                run_version=clarified.active_run_version,
                type=RunEventType.CLARIFICATION_NEEDED,
                payload={
                    "content": response.assistant_message,
                    "map_session": response.map_session.model_dump(mode="json")
                    if response.map_session is not None
                    else None,
                    "operation": response.operation.model_dump(mode="json"),
                    "task_snapshot": response.task_snapshot.model_dump(mode="json")
                    if response.task_snapshot is not None
                    else None,
                    "visualization_update": response.visualization_update.model_dump(mode="json")
                    if response.visualization_update is not None
                    else None,
                },
            )
            return
        if self._response_failed(response):
            failed = self.run_repository.mark_failed(
                run_id,
                "agent_operation_failed",
                response.operation.message if response.operation is not None else "Failed",
            )
            await self._publish_progress(failed, RunProgressStage.FAILED)
            await self.event_publisher.publish(
                conversation_id=failed.conversation_id,
                run_id=failed.run_id,
                run_version=failed.active_run_version,
                type=RunEventType.ERROR,
                payload={
                    "code": "agent_operation_failed",
                    "message": response.operation.message
                    if response.operation is not None
                    else "Failed",
                    "operation": response.operation.model_dump(mode="json")
                    if response.operation is not None
                    else None,
                },
            )
            return
        completed = self.run_repository.mark_completed(run_id)
        await self._publish_progress(completed, RunProgressStage.COMPLETED)
        await self.event_publisher.publish(
            conversation_id=completed.conversation_id,
            run_id=completed.run_id,
            run_version=completed.active_run_version,
            type=RunEventType.COMPLETED,
            payload={
                "state": completed.state.value,
                "map_session": response.map_session.model_dump(mode="json")
                if response.map_session is not None
                else None,
                "operation": response.operation.model_dump(mode="json")
                if response.operation is not None
                else None,
                "memory_snapshot": response.memory_snapshot,
                "context_usage": response.context_usage.model_dump(mode="json")
                if response.context_usage is not None
                else None,
                "task_snapshot": response.task_snapshot.model_dump(mode="json")
                if response.task_snapshot is not None
                else None,
                "failure_diagnostic": response.failure_diagnostic.model_dump(mode="json")
                if response.failure_diagnostic is not None
                else None,
                "visualization_update": response.visualization_update.model_dump(mode="json")
                if response.visualization_update is not None
                else None,
                "context_revision": response.context_revision,
            },
        )

    # -------------------------------------------------------------------------
    async def _publish_response(self, snapshot, response: ChatTurnResponse) -> None:
        await self._publish_progress(snapshot, RunProgressStage.DRAFTING_ANSWER)
        await self.event_publisher.publish(
            conversation_id=snapshot.conversation_id,
            run_id=snapshot.run_id,
            run_version=snapshot.active_run_version,
            type=RunEventType.ASSISTANT_TEXT_COMPLETED,
            payload={
                "content": response.assistant_message,
                "operation": response.operation.model_dump(mode="json")
                if response.operation is not None
                else None,
            },
        )

    # -------------------------------------------------------------------------
    async def _publish_progress(self, snapshot, stage: RunProgressStage) -> None:
        await self.event_publisher.publish(
            conversation_id=snapshot.conversation_id,
            run_id=snapshot.run_id,
            run_version=snapshot.active_run_version,
            type=RunEventType.PROGRESS,
            payload={"stage": stage.value, "label": RUN_PROGRESS_LABELS[stage]},
        )

    # -------------------------------------------------------------------------
    async def _publish_cancelled(self, snapshot) -> None:
        cancelled = self.run_repository.request_cancel(snapshot.run_id)
        await self._publish_progress(cancelled, RunProgressStage.CANCELLED)
        await self.event_publisher.publish(
            conversation_id=cancelled.conversation_id,
            run_id=cancelled.run_id,
            run_version=cancelled.active_run_version,
            type=RunEventType.CANCELLED,
            payload={"state": cancelled.state.value},
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _response_failed(response: ChatTurnResponse) -> bool:
        operation = response.operation
        if operation is None:
            return False
        return operation.status == "failed" or operation.kind == "error"
