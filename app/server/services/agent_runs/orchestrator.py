from __future__ import annotations

import asyncio
import hashlib
import json
from contextlib import suppress
from typing import Any, cast

from server.common.typing import is_json_object
from server.contracts.runs import AgentRunSnapshot
from server.domain.agent.trace import AgentCheckpoint, AgentTraceEvent
from server.domain.agent.capability_route import AgentRunState as NativeRunState
from server.contracts.chat import ChatTurnRequest, ChatTurnResponse
from server.contracts.events import (
    RUN_PROGRESS_LABELS,
    RunEventType,
    RunProgressStage,
    RunEventVisibility,
)
from server.repositories.agent_runs import AgentRunRepository
from server.repositories.agent_steering import AgentSteeringRepository
from server.repositories.conversations import ConversationRepository
from server.services.agent.native_orchestrator import NativeAgentOrchestrator
from server.services.agent_runs.events import RunEventPublisher
from server.services.agent_runs.render_completion import (
    RenderAcknowledgementError,
    RenderCompletionService,
)
from server.services.geospatial.providers.base import ProviderAuthError, ProviderError

###############################################################################
class AgentRunOrchestrator:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        agent_orchestrator: NativeAgentOrchestrator,
        run_repository: AgentRunRepository,
        event_publisher: RunEventPublisher,
        conversation_repository: ConversationRepository,
        steering_repository: AgentSteeringRepository | None = None,
        render_completion_service: RenderCompletionService | None = None,
        defer_map_completion: bool = False,
    ) -> None:
        self.agent_orchestrator = agent_orchestrator
        self.run_repository = run_repository
        self.event_publisher = event_publisher
        self.conversation_repository = conversation_repository
        self.steering_repository = steering_repository
        self.render_completion_service = render_completion_service
        self.defer_map_completion = defer_map_completion

    # -------------------------------------------------------------------------
    async def execute_run(self, run_id: str) -> ChatTurnResponse | None:
        snapshot = self.run_repository.get_run(run_id)
        if snapshot is None:
            return None
        if snapshot.cancel_requested_at is not None:
            await self._publish_cancelled(snapshot)
            return None
        expected_version = snapshot.active_run_version
        checkpoint = self._latest_checkpoint(run_id, expected_version)
        snapshot, transitioned = self.run_repository.mark_started_if_current(
            run_id, expected_version
        )
        if not transitioned:
            if snapshot.cancel_requested_at is not None:
                await self._publish_cancelled(snapshot)
            elif snapshot.active_run_version != expected_version:
                return await self.execute_run(run_id)
            return None
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
        context_events: asyncio.Queue[
            tuple[RunEventType, dict[str, Any], RunEventVisibility]
        ] = asyncio.Queue()

        async def publish_context_events() -> None:
            while True:
                event_type, payload, visibility = await context_events.get()
                try:
                    await self.event_publisher.publish(
                        conversation_id=snapshot.conversation_id,
                        run_id=snapshot.run_id,
                        run_version=snapshot.active_run_version,
                        type=event_type,
                        visibility=visibility,
                        payload=payload,
                    )
                except Exception:
                    # Context telemetry must not turn a valid agent result into
                    # a failed run when the event sink is unavailable.
                    pass
                finally:
                    context_events.task_done()

        def on_agent_progress(event: str, payload: dict[str, Any]) -> None:
            if event == "context_usage":
                context_events.put_nowait(
                    (RunEventType.CONTEXT_USAGE, dict(payload), RunEventVisibility.USER)
                )
            elif event == "stage":
                context_events.put_nowait(
                    (
                        RunEventType.TRACE,
                        {"kind": "stage", **dict(payload)},
                        RunEventVisibility.INTERNAL,
                    )
                )

        async def on_agent_trace(trace: AgentTraceEvent) -> None:
            """Persist the redacted trace and publish concise tool progress."""

            current = self.run_repository.get_run(run_id)
            if (
                current is None
                or current.active_run_version != snapshot.active_run_version
                or current.cancel_requested_at is not None
            ):
                return
            await self._publish_trace(current, trace)
            if trace.kind not in {"tool_selected", "tool_result"}:
                return
            completed = trace.kind == "tool_result"
            await self.event_publisher.publish(
                conversation_id=current.conversation_id,
                run_id=current.run_id,
                run_version=current.active_run_version,
                type=(
                    RunEventType.TOOL_COMPLETED
                    if completed
                    else RunEventType.TOOL_STARTED
                ),
                payload=self._tool_progress_payload(trace, completed=completed),
            )

        def run_state_check() -> str | None:
            latest = self.run_repository.get_run(run_id)
            if latest is None or latest.cancel_requested_at is not None:
                return "cancelled"
            if latest.active_run_version != snapshot.active_run_version:
                return "superseded"
            return None

        async def on_checkpoint(state: NativeRunState) -> None:
            """Persist each safe native boundary in the internal run log."""

            current = self.run_repository.get_run(run_id)
            if (
                current is None
                or current.active_run_version != snapshot.active_run_version
                or current.cancel_requested_at is not None
            ):
                return
            run_state = state.checkpoint()
            await self._publish_trace(
                current,
                AgentTraceEvent(
                    kind="checkpoint",
                    run_id=current.run_id,
                    run_version=current.active_run_version,
                    sequence=max(1, state.transitions),
                    payload=AgentCheckpoint(
                        run_id=current.run_id,
                        conversation_id=current.conversation_id,
                        run_version=current.active_run_version,
                        conversation_state={},
                        run_state=run_state,
                        state_hash=_hash_json(run_state),
                        completed_call_fingerprints=list(
                            state.successful_fingerprints
                        )[-32:],
                        completion_reason=state.termination_reason,
                    ).model_dump(mode="json"),
                ),
            )

        context_event_task = asyncio.create_task(publish_context_events())
        try:
            response = await self.agent_orchestrator.run_turn(
                ChatTurnRequest(
                    message=self._request_message(snapshot),
                    datetime=snapshot.created_at.isoformat(),
                    timezone=snapshot.request_timezone,
                    request_id=run_id,
                    title=snapshot.original_request[:120],
                    conversation_id=snapshot.conversation_id,
                ),
                progress_callback=on_agent_progress,
                trace_callback=on_agent_trace,
                defer_map_commit=True,
                agent_run_id=run_id,
                agent_run_version=snapshot.active_run_version,
                checkpoint=checkpoint,
                checkpoint_callback=on_checkpoint,
                run_state_check=run_state_check,
            )
        except Exception as exc:
            latest = self.run_repository.get_run(run_id) or snapshot
            if latest.cancel_requested_at is not None:
                await self._publish_cancelled(latest)
                return None
            safe_message = self._safe_failure_message(exc)
            failed, transitioned = self.run_repository.mark_failed_if_current(
                run_id,
                snapshot.active_run_version,
                "agent_execution_failed",
                safe_message,
            )
            if not transitioned:
                if failed.cancel_requested_at is not None:
                    await self._publish_cancelled(failed)
                elif failed.active_run_version != snapshot.active_run_version:
                    return await self.execute_run(run_id)
                return None
            await self.event_publisher.publish(
                conversation_id=latest.conversation_id,
                run_id=latest.run_id,
                run_version=latest.active_run_version,
                type=RunEventType.ERROR,
                payload={
                    "code": "agent_execution_failed",
                    "message": safe_message,
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
            return None
        finally:
            await context_events.join()
            context_event_task.cancel()
            with suppress(asyncio.CancelledError):
                await context_event_task

        latest = self.run_repository.get_run(run_id) or snapshot
        if latest.cancel_requested_at is not None:
            await self._publish_cancelled(latest)
            return None
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
            return await self.execute_run(run_id)

        if (
            self.defer_map_completion
            and self.render_completion_service is not None
            and response.map_session is not None
            and response.operation.kind == "map_session"
            and response.operation.status in {"success", "partial", "pending"}
        ):
            if self.render_completion_service.has_blocking_data_failure(
                response.map_session
            ):
                failed_operation = response.operation.model_copy(
                    update={
                        "status": "failed",
                        "message": (
                            "The requested map data was unavailable; the previous map "
                            "remains available."
                        ),
                    }
                )
                response = response.model_copy(
                    update={
                        "map_session": None,
                        "operation": failed_operation,
                    }
                )
            elif not self.render_completion_service.requires_browser_ack(
                response.map_session
            ):
                # Metadata-only products (for example point-sampled weather)
                # are valid data responses but have no browser-visible layer to
                # acknowledge. Keep their explanatory response and finalize it
                # through the ordinary path instead of leaving the run pending
                # forever with an impossible render requirement.
                metadata_operation = response.operation.model_copy(
                    update={
                        "status": "partial",
                        "message": (
                            response.operation.message
                            + " The requested product is metadata-only, so no area overlay was created."
                        ),
                    }
                )
                metadata_state = (
                    response.conversation_state.model_copy(
                        update={"committed_map_session": None}
                    )
                    if response.conversation_state is not None
                    else None
                )
                response = response.model_copy(
                    update={
                        "map_session": None,
                        "operation": metadata_operation,
                        "conversation_state": metadata_state,
                    }
                )

        if (
            self.defer_map_completion
            and self.render_completion_service is not None
            and response.map_session is not None
            and response.operation.kind == "map_session"
            and response.operation.status in {"success", "partial", "pending"}
        ):
            final_response_payload = response.model_dump(mode="json")
            try:
                presentation, prepared = self.render_completion_service.prepare(
                    run_id=run_id,
                    run_version=snapshot.active_run_version,
                    response_payload=final_response_payload,
                )
            except (RenderAcknowledgementError, ValueError) as exc:
                failed, transitioned = self.run_repository.mark_failed_if_current(
                    run_id,
                    snapshot.active_run_version,
                    "map_preparation_failed",
                    str(exc),
                    presentation_status="failed",
                )
                if transitioned:
                    await self._publish_progress(failed, RunProgressStage.FAILED)
                    await self.event_publisher.publish(
                        conversation_id=failed.conversation_id,
                        run_id=failed.run_id,
                        run_version=failed.active_run_version,
                        type=RunEventType.ERROR,
                        payload={
                            "code": "map_preparation_failed",
                            "message": "The requested map could not be prepared for rendering.",
                        },
                    )
                return None
            if not prepared:
                # A cancellation or version change won the compare-and-swap;
                # never let the normal completion path promote this stale
                # candidate.
                return None
            if prepared:
                loading_operation = response.operation.model_copy(
                    update={
                        "status": "pending",
                        "message": "Data prepared; the map is loading.",
                    }
                )
                loading_response = response.model_copy(
                    update={
                        "assistant_message": "Data prepared; the map is loading.",
                        "operation": loading_operation,
                    }
                )
                await self._publish_response(snapshot, loading_response)
                awaiting = self.run_repository.get_run(run_id) or snapshot
                await self._publish_progress(awaiting, RunProgressStage.AWAITING_RENDER)
                await self.event_publisher.publish(
                    conversation_id=awaiting.conversation_id,
                    run_id=awaiting.run_id,
                    run_version=awaiting.active_run_version,
                    type=RunEventType.MAP_PREPARED,
                    payload={
                        "presentation": presentation,
                        "map_session": response.map_session.model_dump(mode="json"),
                        "operation": loading_operation.model_dump(mode="json"),
                    },
                )
                await self._publish_trace(
                    awaiting,
                    AgentTraceEvent(
                        kind="run_suspended",
                        run_id=awaiting.run_id,
                        run_version=awaiting.active_run_version,
                        sequence=3,
                        payload={
                            "reason": "awaiting_render",
                            "map_session_id": response.map_session.session_id,
                            "collection_revision": response.map_session.overlay_collection.revision,
                            "render_attempts": int(
                                (presentation.get("render_attempts") or 0)
                            ),
                        },
                    ),
                )
                return loading_response
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
                    conversation_state=(
                        response.conversation_state.model_dump(mode="json")
                        if response.conversation_state is not None
                        else {}
                    ),
                    run_state=(
                        response.execution_trace.get("checkpoint")
                        if isinstance(response.execution_trace, dict)
                        and isinstance(
                            response.execution_trace.get("checkpoint"), dict
                        )
                        else None
                    ),
                    state_hash=hashlib.sha256(
                        json.dumps(
                            response.conversation_state.model_dump(mode="json")
                            if response.conversation_state is not None
                            else {},
                            sort_keys=True,
                            separators=(",", ":"),
                            default=str,
                        ).encode("utf-8")
                    ).hexdigest(),
                    completion_reason=(
                        "clarification_required"
                        if response.operation.kind == "clarification"
                        else None
                    ),
                ).model_dump(mode="json"),
            ),
        )
        await self._publish_response(latest, response)
        if response.operation.kind == "clarification":
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
                    **self._response_payload(response),
                },
            )
            return
        if self._response_failed(response):
            terminal_presentation_status = (
                response.presentation_status
                if response.presentation_status in {"failed", "render_timeout"}
                else None
            )
            failed, transitioned = self.run_repository.mark_failed_if_current(
                run_id,
                snapshot.active_run_version,
                "agent_operation_failed",
                response.operation.message,
                **(
                    {"presentation_status": terminal_presentation_status}
                    if terminal_presentation_status is not None
                    else {}
                ),
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
                    "message": response.operation.message,
                    **self._response_payload(response),
                },
            )
            return
        terminal_presentation_status = (
            response.presentation_status
            if response.presentation_status in {"ready", "failed", "render_timeout"}
            else None
        )
        if terminal_presentation_status is None:
            # Keep the legacy repository seam usable for lightweight worker
            # doubles and non-render transports; ``not_requested`` is already
            # the repository default and carries no additional state.
            completed, transitioned = self.run_repository.mark_completed_if_current(
                run_id, snapshot.active_run_version
            )
        else:
            completed, transitioned = self.run_repository.mark_completed_if_current(
                run_id,
                snapshot.active_run_version,
                presentation_status=terminal_presentation_status,
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
                **self._response_payload(response),
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
                    "operation_status": response.operation.status,
                    "model_calls": self._model_call_count(response),
                    "tool_calls": len(
                        (response.tool_payload or {}).get("tool_calls", [])
                    ),
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
                "operation": response.operation.model_dump(mode="json"),
            },
        )

        await self._publish_trace(
            snapshot,
            AgentTraceEvent(
                kind="stage",
                run_id=snapshot.run_id,
                run_version=snapshot.active_run_version,
                sequence=3,
                payload={
                    "stage": "frontend_delivery",
                    "status": "completed",
                    "request_id": response.request_id,
                },
            ),
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _response_payload(response: ChatTurnResponse) -> dict[str, Any]:
        """Return the canonical native response shape for run events."""

        payload = response.model_dump(mode="json", exclude_none=True)
        payload["content"] = response.assistant_message
        return payload

    # -------------------------------------------------------------------------
    @staticmethod
    def _tool_progress_payload(
        trace: AgentTraceEvent,
        *,
        completed: bool,
    ) -> dict[str, Any]:
        """Build the user-visible, non-sensitive projection of a tool trace."""

        raw = trace.payload
        evidence_refs = raw.get("evidence_refs")
        safe_refs = (
            [
                str(item)
                for item in cast(list[Any], evidence_refs)
                if str(item).strip()
            ][:16]
            if isinstance(evidence_refs, list)
            else []
        )
        status = str(raw.get("status") or ("success" if completed else "running"))
        payload: dict[str, Any] = {
            "call_id": trace.call_id or "",
            "tool_name": trace.tool_name or "",
            "task_id": trace.task_id,
            "iteration": trace.iteration,
            "label": _tool_label(trace.tool_name),
            "status": status if completed else "running",
            "started_at": trace.timestamp.isoformat(),
        }
        if completed:
            payload.update(
                {
                    "summary": str(raw.get("summary") or "")[:1_000],
                    "duration_ms": raw.get("duration_ms"),
                    "evidence_refs": safe_refs,
                    "error": raw.get("error"),
                    "recovery": raw.get("recovery"),
                    "completed_at": trace.timestamp.isoformat(),
                }
            )
        return payload

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
        cancelled, transitioned = self.run_repository.request_cancel_once(
            snapshot.run_id
        )
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
        """Persist one operational event in the canonical run event log."""

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

    # -------------------------------------------------------------------------
    def _latest_checkpoint(
        self, run_id: str, run_version: int
    ) -> dict[str, Any] | None:
        repository = getattr(self.event_publisher, "event_repository", None)
        loader = getattr(repository, "get_latest_checkpoint_state", None)
        if not callable(loader):
            return None
        try:
            value = loader(run_id, run_version=run_version)
        except Exception:
            return None
        return value if is_json_object(value) else None

    # -------------------------------------------------------------------------
    @staticmethod
    def _model_call_count(response: ChatTurnResponse) -> int:
        payload = response.tool_payload or {}
        iterations = payload.get("iterations")
        return int(iterations) if isinstance(iterations, int) else 1

    # -------------------------------------------------------------------------
    @staticmethod
    def _safe_failure_message(exc: Exception) -> str:
        if isinstance(exc, ProviderAuthError):
            return "The map data provider requires valid credentials. Configure them in Settings under Geospatial Access."
        if isinstance(exc, ProviderError):
            return "The map data provider could not complete this request. Try again later."
        text = str(exc).strip().lower()
        if "credential" in text or "api key" in text or "authentication" in text:
            return "The configured agent provider is not ready. Open Settings and configure its credential."
        if "timeout" in text:
            return "The configured agent provider timed out before the request could be completed."
        return "The agent could not complete this request."

    # -------------------------------------------------------------------------
    @staticmethod
    def _response_failed(response: ChatTurnResponse) -> bool:
        return (
            response.operation.status == "failed"
            or response.operation.kind == "error"
        )

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


def _hash_json(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
    ).hexdigest()


def _tool_label(tool_name: str | None) -> str:
    normalized = " ".join(str(tool_name or "tool").replace("_", " ").split())
    return normalized[:1].upper() + normalized[1:]
