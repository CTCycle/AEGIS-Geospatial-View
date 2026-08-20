from __future__ import annotations

from server.contracts.runs import AgentRunSnapshot
from server.domain.agent.trace import AgentCheckpoint, AgentTraceEvent
from server.contracts.chat import ChatTurnRequest, ChatTurnResponse
from server.contracts.events import RUN_PROGRESS_LABELS, RunEventType, RunProgressStage, RunEventVisibility
from server.repositories.agent_runs import AgentRunRepository
from server.repositories.agent_steering import AgentSteeringRepository
from server.repositories.conversations import ConversationRepository
from server.services.agent.orchestrator import AgentOrchestrator
from server.services.agent_runs.events import RunEventPublisher

import hashlib
import json

###############################################################################
class AgentRunOrchestrator:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        agent_orchestrator: AgentOrchestrator,
        run_repository: AgentRunRepository,
        event_publisher: RunEventPublisher,
        conversation_repository: ConversationRepository,
        steering_repository: AgentSteeringRepository | None = None,
    ) -> None:
        self.agent_orchestrator = agent_orchestrator
        self.run_repository = run_repository
        self.event_publisher = event_publisher
        self.conversation_repository = conversation_repository
        self.steering_repository = steering_repository

    # -------------------------------------------------------------------------
    async def execute_run(self, run_id: str) -> None:
        snapshot = self.run_repository.get_run(run_id)
        if snapshot is None:
            return
        if snapshot.cancel_requested_at is not None:
            await self._publish_cancelled(snapshot)
            return
        expected_version = snapshot.active_run_version
        snapshot, transitioned = self.run_repository.mark_started_if_current(
            run_id, expected_version
        )
        if not transitioned:
            if snapshot.cancel_requested_at is not None:
                await self._publish_cancelled(snapshot)
            elif snapshot.active_run_version != expected_version:
                await self.execute_run(run_id)
            return
        await self._publish_progress(snapshot, RunProgressStage.UNDERSTANDING_REQUEST)
        await self._publish_trace(
            snapshot,
            AgentTraceEvent(
                kind="run_started",
                run_id=snapshot.run_id,
                run_version=snapshot.active_run_version,
                sequence=0,
                payload={
                    "objective": snapshot.original_request,
                    "request_length": len(snapshot.aggregated_request),
                },
            ),
        )
        try:
            response = await self.agent_orchestrator.run_turn(
                ChatTurnRequest(
                    message=self._request_message(snapshot),
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
            failed, transitioned = self.run_repository.mark_failed_if_current(
                run_id,
                snapshot.active_run_version,
                "agent_execution_failed",
                str(exc),
            )
            if not transitioned:
                if failed.cancel_requested_at is not None:
                    await self._publish_cancelled(failed)
                elif failed.active_run_version != snapshot.active_run_version:
                    await self.execute_run(run_id)
                return
            await self.event_publisher.publish(
                conversation_id=latest.conversation_id,
                run_id=latest.run_id,
                run_version=latest.active_run_version,
                type=RunEventType.ERROR,
                payload={
                    "code": "agent_execution_failed",
                    "message": self._safe_failure_message(exc),
                },
            )
            await self._publish_trace(
                latest,
                AgentTraceEvent(
                    kind="completion",
                    run_id=latest.run_id,
                    run_version=latest.active_run_version,
                    sequence=1,
                    payload={
                        "completion_reason": "required_task_failed",
                        "error_type": type(exc).__name__,
                    },
                ),
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
        await self._publish_trace(
            latest,
            AgentTraceEvent(
                kind="checkpoint",
                run_id=latest.run_id,
                run_version=latest.active_run_version,
                sequence=1,
                payload=AgentCheckpoint(
                    run_id=latest.run_id,
                    conversation_id=latest.conversation_id,
                    run_version=latest.active_run_version,
                    task_snapshot=(
                        response.task_snapshot.model_dump(mode="json")
                        if response.task_snapshot is not None
                        else {"schema_version": 2, "tasks": []}
                    ),
                    state_hash=hashlib.sha256(
                        json.dumps(
                            response.task_snapshot.model_dump(mode="json")
                            if response.task_snapshot is not None
                            else {},
                            sort_keys=True,
                            separators=(",", ":"),
                            default=str,
                        ).encode("utf-8")
                    ).hexdigest(),
                    completion_reason=(
                        "clarification_required"
                        if response.operation is not None
                        and response.operation.kind == "clarification"
                        else None
                    ),
                ).model_dump(mode="json"),
            ),
        )
        await self._publish_response(latest, response)
        if response.operation is not None and response.operation.kind == "clarification":
            clarified, transitioned = self.run_repository.mark_completed_if_current(
                run_id, snapshot.active_run_version
            )
            if not transitioned:
                if clarified.cancel_requested_at is not None:
                    await self._publish_cancelled(clarified)
                elif clarified.active_run_version != snapshot.active_run_version:
                    await self.execute_run(run_id)
                return
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
                    "decision": response.decision.model_dump(mode="json"),
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
            failed, transitioned = self.run_repository.mark_failed_if_current(
                run_id,
                snapshot.active_run_version,
                "agent_operation_failed",
                response.operation.message if response.operation is not None else "Failed",
            )
            if not transitioned:
                if failed.cancel_requested_at is not None:
                    await self._publish_cancelled(failed)
                elif failed.active_run_version != snapshot.active_run_version:
                    await self.execute_run(run_id)
                return
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
        completed, transitioned = self.run_repository.mark_completed_if_current(
            run_id, snapshot.active_run_version
        )
        if not transitioned:
            if completed.cancel_requested_at is not None:
                await self._publish_cancelled(completed)
            elif completed.active_run_version != snapshot.active_run_version:
                await self.execute_run(run_id)
            return
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
                "decision": response.decision.model_dump(mode="json"),
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

        await self._publish_trace(
            completed,
            AgentTraceEvent(
                kind="completion",
                run_id=completed.run_id,
                run_version=completed.active_run_version,
                sequence=2,
                payload={
                    "completion_reason": "completed",
                    "operation_status": response.operation.status
                    if response.operation is not None
                    else None,
                    "model_calls": self._model_call_count(response),
                    "tool_calls": len((response.tool_payload or {}).get("tool_calls", [])),
                },
            ),
        )

    # -------------------------------------------------------------------------
    async def _publish_response(
        self, snapshot: AgentRunSnapshot, response: ChatTurnResponse
    ) -> None:
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
    async def _publish_progress(
        self, snapshot: AgentRunSnapshot, stage: RunProgressStage
    ) -> None:
        await self.event_publisher.publish(
            conversation_id=snapshot.conversation_id,
            run_id=snapshot.run_id,
            run_version=snapshot.active_run_version,
            type=RunEventType.PROGRESS,
            payload={"stage": stage.value, "label": RUN_PROGRESS_LABELS[stage]},
        )

    # -------------------------------------------------------------------------
    async def _publish_cancelled(self, snapshot: AgentRunSnapshot) -> None:
        cancelled, transitioned = self.run_repository.request_cancel_once(snapshot.run_id)
        if not transitioned:
            return
        await self._publish_progress(cancelled, RunProgressStage.CANCELLED)
        await self.event_publisher.publish(
            conversation_id=cancelled.conversation_id,
            run_id=cancelled.run_id,
            run_version=cancelled.active_run_version,
            type=RunEventType.CANCELLED,
            payload={"state": cancelled.state.value},
        )

    # -------------------------------------------------------------------------
    async def _publish_trace(
        self,
        snapshot: AgentRunSnapshot,
        trace: AgentTraceEvent,
    ) -> None:
        """Persist operational metadata without affecting user-visible events."""

        try:
            await self.event_publisher.publish(
                conversation_id=snapshot.conversation_id,
                run_id=snapshot.run_id,
                run_version=snapshot.active_run_version,
                type=(
                    RunEventType.CHECKPOINT
                    if trace.kind == "checkpoint"
                    else RunEventType.TRACE
                ),
                visibility=RunEventVisibility.INTERNAL,
                payload=trace.model_dump(mode="json"),
            )
        except Exception:
            # Observability is best effort.  A storage hiccup must not turn a
            # successful geospatial response into an agent failure.
            return

    # -------------------------------------------------------------------------
    @staticmethod
    def _model_call_count(response: ChatTurnResponse) -> int:
        payload = response.tool_payload or {}
        iterations = payload.get("iterations")
        return int(iterations) if isinstance(iterations, int) else 1

    # -------------------------------------------------------------------------
    @staticmethod
    def _safe_failure_message(exc: Exception) -> str:
        text = str(exc).strip().lower()
        if "credential" in text or "api key" in text or "authentication" in text:
            return "The configured agent provider is not ready. Open Model Settings and configure its credential."
        if "timeout" in text:
            return "The configured agent provider timed out before the request could be completed."
        return "The agent could not complete this request."

    # -------------------------------------------------------------------------
    @staticmethod
    def _response_failed(response: ChatTurnResponse) -> bool:
        operation = response.operation
        if operation is None:
            return False
        return operation.status == "failed" or operation.kind == "error"

    # -------------------------------------------------------------------------
    def _request_message(self, snapshot: AgentRunSnapshot) -> str:
        """Use a structured delta on rerun only after it was durably applied."""

        if self.steering_repository is None:
            return snapshot.aggregated_request
        messages = self.steering_repository.list_steering_messages(snapshot.run_id)
        latest = messages[-1] if messages else None
        if latest is not None and latest.state_delta_applied:
            return latest.content
        return snapshot.aggregated_request
