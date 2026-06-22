from __future__ import annotations

from server.domain.agent_runs import TERMINAL_RUN_STATES
from server.domain.run_events import RUN_PROGRESS_LABELS, RunEventType, RunProgressStage
from server.domain.steering import SteeringMessageRequest, SteeringMessageResponse
from server.repositories.agent_runs import AgentRunRepository
from server.repositories.agent_steering import AgentSteeringRepository
from server.services.agent_runs.aggregation import AggregatedRequestService
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
    ) -> None:
        self.run_repository = run_repository
        self.steering_repository = steering_repository
        self.aggregation_service = aggregation_service
        self.event_publisher = event_publisher

    # -------------------------------------------------------------------------
    async def steer(
        self,
        conversation_id: str,
        run_id: str,
        payload: SteeringMessageRequest,
    ) -> SteeringMessageResponse:
        snapshot = self.run_repository.get_run(run_id)
        if snapshot is None or snapshot.conversation_id != conversation_id:
            raise RunNotFoundError("Run not found.")
        if snapshot.state in TERMINAL_RUN_STATES:
            raise RunConflictError("Run is already terminal.")
        existing = (
            self.steering_repository.find_by_client_mutation_id(run_id, payload.client_mutation_id)
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
            )
        next_version = snapshot.active_run_version + 1
        steering = self.steering_repository.append_steering_message(
            run_id,
            payload.message,
            payload.client_mutation_id,
            next_version,
        )
        messages = [item.content for item in self.steering_repository.list_steering_messages(run_id)]
        aggregate = self.aggregation_service.build_aggregated_request(
            snapshot.original_request,
            messages,
        )
        updated = self.run_repository.update_aggregated_request(run_id, aggregate, next_version)
        await self.event_publisher.publish(
            conversation_id=conversation_id,
            run_id=run_id,
            run_version=updated.active_run_version,
            type=RunEventType.REQUEST_UPDATED,
            payload={
                "stage": RunProgressStage.REQUEST_UPDATED.value,
                "label": RUN_PROGRESS_LABELS[RunProgressStage.REQUEST_UPDATED],
                "steering_id": steering.steering_id,
                "aggregated_request": aggregate,
            },
        )
        return SteeringMessageResponse(
            conversation_id=conversation_id,
            run_id=run_id,
            steering_id=steering.steering_id,
            run_version=updated.active_run_version,
            aggregated_request=aggregate,
            state=updated.state,
        )
