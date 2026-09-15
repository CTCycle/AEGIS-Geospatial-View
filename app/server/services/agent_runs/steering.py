from __future__ import annotations

from typing import Any

from server.common.typing import is_json_array, is_json_object
from server.contracts.runs import TERMINAL_RUN_STATES
from server.contracts.events import RUN_PROGRESS_LABELS, RunEventType, RunProgressStage
from server.domain.steering import (
    SteeringDelta,
    SteeringMessageRequest,
    SteeringMessageResponse,
    classify_steering_delta,
)
from server.repositories.agent_runs import AgentRunRepository
from server.repositories.agent_steering import AgentSteeringRepository
from server.repositories.conversations import ConversationRepository
from server.services.agent_runs.aggregation import AggregatedRequestService
from server.domain.agent.conversation import ConversationState
from server.services.agent_runs.events import RunEventPublisher
from server.services.agent_runs.exceptions import RunConflictError, RunNotFoundError

###############################################################################
class RunSteeringService:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        run_repository: AgentRunRepository,
        steering_repository: AgentSteeringRepository,
        aggregation_service: AggregatedRequestService,
        event_publisher: RunEventPublisher,
        conversation_repository: ConversationRepository | None = None,
    ) -> None:
        self.run_repository = run_repository
        self.steering_repository = steering_repository
        self.aggregation_service = aggregation_service
        self.event_publisher = event_publisher
        self.conversation_repository = conversation_repository

    # -------------------------------------------------------------------------
    async def steer(
        self,
        conversation_id: str,
        run_id: str,
        payload: SteeringMessageRequest,
    ) -> SteeringMessageResponse:
        steering = None
        run_version = 0
        aggregate = ""
        updated = None
        delta = classify_steering_delta(payload.message)
        for _attempt in range(3):
            snapshot = self.run_repository.get_run(run_id)
            if snapshot is None or snapshot.conversation_id != conversation_id:
                raise RunNotFoundError("Run not found.")
            if snapshot.state in TERMINAL_RUN_STATES:
                raise RunConflictError("Run is already terminal.")
            existing = (
                self.steering_repository.find_by_client_mutation_id(
                    run_id, payload.client_mutation_id
                )
                if payload.client_mutation_id
                else None
            )
            if existing is not None:
                return SteeringMessageResponse(
                    conversation_id=conversation_id,
                    run_id=run_id,
                    steering_id=existing.steering_id,
                    run_version=existing.run_version,
                    aggregated_request=snapshot.aggregated_request,
                    state=snapshot.state,
                    duplicate=True,
                    delta=delta,
                    state_delta_applied=existing.state_delta_applied,
                )
            next_version = snapshot.active_run_version + 1
            messages = [
                item.content
                for item in self.steering_repository.list_steering_messages(run_id)
            ]
            messages.append(payload.message)
            aggregate = self.aggregation_service.build_aggregated_request(
                snapshot.original_request,
                messages,
            )
            try:
                steering, run_version, aggregate = (
                    self.steering_repository.append_and_update_run(
                        run_id=run_id,
                        content=payload.message,
                        client_mutation_id=payload.client_mutation_id,
                        run_version=next_version,
                        aggregated_request=aggregate,
                        expected_run_version=snapshot.active_run_version,
                    )
                )
            except ValueError as exc:
                if str(exc) != "Run version conflict.":
                    raise RunConflictError(str(exc)) from exc
                continue
            updated = self.run_repository.get_run(run_id)
            if updated is None:
                raise RunNotFoundError("Run not found.")
            break
        if steering is None or updated is None:
            raise RunConflictError("Concurrent run update could not be applied.")
        state_delta_applied = self._apply_state_delta(conversation_id, delta)
        if state_delta_applied:
            steering = self.steering_repository.mark_state_delta_applied(
                steering.steering_id
            )
        await self.event_publisher.publish(
            conversation_id=conversation_id,
            run_id=run_id,
            run_version=run_version,
            type=RunEventType.REQUEST_UPDATED,
            payload={
                "stage": RunProgressStage.REQUEST_UPDATED.value,
                "label": RUN_PROGRESS_LABELS[RunProgressStage.REQUEST_UPDATED],
                "steering_id": steering.steering_id,
                "aggregated_request": aggregate,
                "delta": delta.model_dump(mode="json"),
                "state_delta_applied": state_delta_applied,
            },
        )
        return SteeringMessageResponse(
            conversation_id=conversation_id,
            run_id=run_id,
            steering_id=steering.steering_id,
            run_version=run_version,
            aggregated_request=aggregate,
            state=updated.state,
            duplicate=False,
            delta=delta,
            state_delta_applied=state_delta_applied,
        )

    # -------------------------------------------------------------------------
    def _apply_state_delta(
        self, conversation_id: str, delta: SteeringDelta
    ) -> bool:
        """Persist only mutations that can be applied without model interpretation."""

        if self.conversation_repository is None or delta.kind not in {
            "scope_change",
            "exclusion",
            "add_dataset",
            "comparison",
        }:
            return False
        try:
            persisted: dict[str, Any] = self.conversation_repository.read_state(
                conversation_id
            )
            state = ConversationState.from_persisted(
                conversation_id,
                persisted.get("conversation_state"),
                revision=int(persisted.get("context_revision") or 0),
            )
            history = state.constraints.get("steering_history")
            steering_history: list[dict[str, Any]] = []
            if is_json_array(history):
                steering_history.extend(
                    dict(item) for item in history if is_json_object(item)
                )
            steering_history.append(
                {
                    "kind": delta.kind,
                    "text": delta.text[:1000],
                    "parameters": dict(delta.parameters),
                    "preserve_evidence": delta.preserve_evidence,
                    "invalidates_scope_dependent_evidence": (
                        delta.invalidates_scope_dependent_evidence
                    ),
                }
            )
            state = state.model_copy(
                update={
                    "revision": int(persisted.get("context_revision") or 0) + 1,
                    "constraints": {
                        **state.constraints,
                        "latest_steering": steering_history[-1],
                        "steering_history": steering_history[-16:],
                    },
                }
            )
            self.conversation_repository.write_state(
                conversation_id,
                expected_revision=int(persisted["context_revision"]),
                conversation_state=state.model_dump(mode="json"),
            )
            return True
        except (KeyError, TypeError, ValueError):
            return False
