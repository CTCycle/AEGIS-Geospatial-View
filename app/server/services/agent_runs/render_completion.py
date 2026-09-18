"""Durable map presentation handshake between the backend and MapLibre."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import hashlib
import json
from typing import Any, cast

from server.common.time import utc_now
from server.contracts.events import RunEventType, RunEventVisibility, RunProgressStage
from server.contracts.geospatial import MapSession
from server.domain.realtime import RealtimeRenderAckPayload
from server.domain.agent.capability_route import AgentGoal, CompletionContract
from server.domain.agent.capability_route import RenderObservation
from server.domain.agent.trace import AgentCheckpoint, AgentTraceEvent
from server.repositories.agent_runs import AgentRunRepository
from server.services.agent.completion import CompletionEvaluator
from server.services.agent_runs.events import RunEventPublisher

###############################################################################
class RenderAcknowledgementError(ValueError):
    """Raised when browser evidence cannot be applied to the prepared run."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "render_ack_rejected",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})

###############################################################################
def _json_object(value: object) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}

###############################################################################
def _json_list(value: object) -> list[Any]:
    return cast(list[Any], value) if isinstance(value, list) else []

###############################################################################
@dataclass(frozen=True)
class RenderAcknowledgementResult:
    run_id: str
    run_version: int
    state: str
    presentation_status: str
    duplicate: bool
    resume_required: bool = False
    observation: RenderObservation | None = None

###############################################################################
class RenderCompletionService:
    """Prepare candidates and atomically promote acknowledged map sessions."""

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        run_repository: AgentRunRepository,
        event_publisher: RunEventPublisher,
        render_ack_timeout_seconds: float = 90.0,
        resume_mode: bool = False,
        max_render_attempts: int = 3,
    ) -> None:
        self.run_repository = run_repository
        self.event_publisher = event_publisher
        self.render_ack_timeout_seconds = max(0.1, float(render_ack_timeout_seconds))
        self.resume_mode = bool(resume_mode)
        self.max_render_attempts = max(1, min(32, int(max_render_attempts)))

    # -------------------------------------------------------------------------
    def prepare(
        self,
        *,
        run_id: str,
        run_version: int,
        response_payload: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        map_session_value: object = response_payload.get("map_session")
        if not isinstance(map_session_value, dict):
            raise RenderAcknowledgementError("A map session is required for render preparation.")
        map_session = cast(dict[str, Any], map_session_value)
        collection = _json_object(map_session.get("overlay_collection"))
        revision = collection.get("revision")
        session_id = map_session.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise RenderAcknowledgementError("Prepared map has no session identity.")
        if not isinstance(revision, int) or revision < 0:
            raise RenderAcknowledgementError("Prepared map has no valid collection revision.")
        candidate_model = MapSession.model_validate(map_session)
        completion_contract = response_payload.get("completion_contract")
        native_goal = response_payload.get("goal")
        render_requirements = CompletionEvaluator.native_candidate_requirements(
            completion_contract=(
                CompletionContract.model_validate(completion_contract)
                if isinstance(completion_contract, dict)
                else None
            ),
            goal=(
                AgentGoal.model_validate(native_goal)
                if isinstance(native_goal, dict)
                else None
            ),
            map_session=candidate_model,
        )
        render_requirements_payload = [
            item.model_dump(mode="json") for item in render_requirements
        ]
        required_overlay_ids = [
            instance.instance_id
            for instance in candidate_model.overlay_collection.instances
            if not RenderCompletionService._metadata_only(instance)
        ]
        presentation = {
            "status": "pending",
            "map_session_id": session_id,
            "collection_revision": revision,
            "pending_response": response_payload,
            "render_attempts": int(
                _json_object(
                    _json_object(response_payload.get("execution_trace")).get(
                        "checkpoint"
                    )
                ).get("render_attempts")
                or 0
            ),
            "render_observations": list(
                _json_list(
                    _json_object(
                        _json_object(response_payload.get("execution_trace")).get(
                            "checkpoint"
                        )
                    ).get("render_observations")
                )
            )[-8:],
            "required_render_checks": {
                "required_sources_loaded": True,
                "required_layers_present": True,
                "viewport_valid": True,
            },
            "required_overlay_ids": required_overlay_ids,
            "completion_requirements": render_requirements_payload,
        }
        _snapshot, transitioned = self.run_repository.prepare_render(
            run_id,
            run_version,
            presentation,
        )
        return presentation, transitioned

    # -------------------------------------------------------------------------
    @classmethod
    def requires_browser_ack(cls, map_session: MapSession) -> bool:
        """Whether this candidate contains a browser-visible requirement.

        Metadata-only products remain useful as textual/data results, but they
        have no visual layer that can satisfy the renderable-geometry
        requirement.  Location-only sessions still need an acknowledgment
        because the viewport itself is the requested presentation.
        """

        instances = map_session.overlay_collection.instances
        return not instances or any(not cls._metadata_only(instance) for instance in instances)

    # -------------------------------------------------------------------------
    @classmethod
    def has_blocking_data_failure(cls, map_session: MapSession) -> bool:
        """Return true when a candidate contains a provider/data failure.

        An unavailable provider is not a metadata product. It must flow through
        the ordinary failed-operation path instead of being finalized as a
        successful metadata-only response.
        """

        for instance in map_session.overlay_collection.instances:
            descriptor = _json_object(getattr(instance, "descriptor", {}))
            status = str(
                descriptor.get("result_status") or descriptor.get("resultStatus") or ""
            ).casefold()
            render_status = str(
                descriptor.get("render_status")
                or descriptor.get("renderStatus")
                or ""
            ).casefold()
            if status in {"unavailable", "error", "failed", "invalid"} or render_status in {
                "unavailable",
                "error",
                "failed",
                "invalid",
            }:
                return True
        return False

    # -------------------------------------------------------------------------
    @staticmethod
    def _metadata_only(instance: Any) -> bool:
        rendering_mode = str(getattr(instance, "rendering_mode", "")).casefold()
        descriptor = _json_object(getattr(instance, "descriptor", {}))
        result_type = str(
            descriptor.get("result_type") or descriptor.get("resultType") or ""
        ).casefold()
        render_status = str(
            descriptor.get("render_status") or descriptor.get("renderStatus") or ""
        ).casefold()
        return (
            rendering_mode in {"metadata-only", "metadata_only"}
            or result_type == "metadata"
            or render_status in {"metadata-only", "metadata_only"}
        )

    # -------------------------------------------------------------------------
    async def acknowledge(
        self,
        conversation_id: str,
        payload: RealtimeRenderAckPayload,
    ) -> RenderAcknowledgementResult:
        acknowledgment = payload.model_dump(mode="json")
        prior_snapshot = self.run_repository.get_run(payload.run_id)
        prior_presentation = _json_object(
            prior_snapshot.presentation if prior_snapshot else None
        )
        prior_attempt = int(
            prior_presentation.get("render_attempts")
            or 0
        )
        pending_response = _json_object(prior_presentation.get("pending_response"))
        pending_checkpoint = _json_object(
            _json_object(pending_response.get("execution_trace")).get("checkpoint")
        )
        action_fingerprint = str(
            pending_checkpoint.get("prepared_map_action_fingerprint") or ""
        ) or None
        # A duplicate of the terminal retry is still idempotent, but a new
        # browser result after the configured bound is a protocol error.  In
        # particular, do not allow a late successful acknowledgment to bypass
        # the same-run render recovery limit.
        if (
            self.resume_mode
            and prior_snapshot is not None
            and prior_attempt >= self.max_render_attempts
            and prior_presentation.get("acknowledgment") != acknowledgment
        ):
            raise RenderAcknowledgementError(
                "Render recovery attempts are exhausted for this run."
            )
        observation = self._observation_from_ack(payload).model_copy(
            update={
                "attempt": prior_attempt + 1,
                "recovery": (
                    "continue"
                    if payload.status == "ready"
                    else "terminal"
                    if prior_attempt + 1 >= self.max_render_attempts
                    else "revise_map"
                ),
                "action_fingerprint": action_fingerprint,
            }
        )
        expire_pending = getattr(self.run_repository, "expire_pending_render", None)
        if callable(expire_pending):
            expire_pending(
                conversation_id=conversation_id,
                run_id=payload.run_id,
                run_version=payload.run_version,
                timeout_seconds=self.render_ack_timeout_seconds,
            )
        try:
            snapshot, duplicate, pending_response = self.run_repository.acknowledge_render(
                conversation_id=conversation_id,
                run_id=payload.run_id,
                run_version=payload.run_version,
                map_session_id=payload.map_session_id,
                collection_revision=payload.collection_revision,
                status=payload.status,
                acknowledgment=acknowledgment,
                resume=self.resume_mode,
                observation=observation.model_dump(mode="json"),
            )
        except ValueError as exc:
            if "does not match the prepared map" in str(exc):
                expected_identity: dict[str, Any] = {}
                if prior_snapshot is not None:
                    expected_identity = {
                        "run_id": prior_snapshot.run_id,
                        "run_version": prior_snapshot.active_run_version,
                        "map_session_id": prior_presentation.get("map_session_id"),
                        "collection_revision": prior_presentation.get("collection_revision"),
                    }
                observed_identity = {
                    "run_id": payload.run_id,
                    "run_version": payload.run_version,
                    "map_session_id": payload.map_session_id,
                    "collection_revision": payload.collection_revision,
                }
                raise RenderAcknowledgementError(
                    str(exc),
                    code="render_ack_mismatch",
                    details={
                        "expected": expected_identity,
                        "observed": observed_identity,
                    },
                ) from exc
            # A browser can report ``ready`` while a deterministic server
            # check still rejects the candidate (for example a missing layer,
            # invisible feature set, or viewport mismatch). In resumable mode
            # that is an actionable render failure, not a terminal protocol
            # error: feed the normalized rejection back into the same run so
            # the model can revise the map. Identity/version/state errors are
            # deliberately left as protocol errors below.
            if not (
                self.resume_mode
                and payload.status == "ready"
                and self._is_render_validation_rejection(str(exc))
            ):
                raise RenderAcknowledgementError(str(exc)) from exc
            failure_payload = payload.model_copy(
                update={
                    "status": "failed",
                    # Preserve browser-provided diagnostics when the server
                    # additionally rejects a ready acknowledgment.  The
                    # resume observation must retain the original cause, not
                    # replace it with a generic backend-validation label.
                    "failure_code": payload.failure_code or "render_validation_failed",
                    "failure_stage": payload.failure_stage or "backend_validation",
                    "failure_summary": (
                        f"{payload.failure_summary}; backend validation: {exc}"
                        if payload.failure_summary
                        else str(exc)
                    )[:500],
                }
            )
            acknowledgment = failure_payload.model_dump(mode="json")
            observation = self._observation_from_ack(failure_payload).model_copy(
                update={
                    "attempt": prior_attempt + 1,
                    "recovery": (
                        "terminal"
                        if prior_attempt + 1 >= self.max_render_attempts
                        else "revise_map"
                    ),
                    "action_fingerprint": action_fingerprint,
                }
            )
            try:
                snapshot, duplicate, pending_response = self.run_repository.acknowledge_render(
                    conversation_id=conversation_id,
                    run_id=payload.run_id,
                    run_version=payload.run_version,
                    map_session_id=payload.map_session_id,
                    collection_revision=payload.collection_revision,
                    status="failed",
                    acknowledgment=acknowledgment,
                    resume=True,
                    observation=observation.model_dump(mode="json"),
                )
            except ValueError as retry_exc:
                raise RenderAcknowledgementError(str(retry_exc)) from retry_exc
        observed_attempt = int(
            _json_object(snapshot.presentation).get("render_attempts")
            or observation.attempt
        )
        observation = observation.model_copy(update={"attempt": observed_attempt})
        if duplicate:
            return RenderAcknowledgementResult(
                run_id=snapshot.run_id,
                run_version=snapshot.active_run_version,
                state=snapshot.state.value,
                presentation_status=snapshot.presentation_status,
                duplicate=True,
                resume_required=False,
                observation=observation,
            )

        if self.resume_mode:
            await self._publish_resume_observation(
                snapshot=snapshot,
                pending_response=pending_response or {},
                observation=observation,
            )
            return RenderAcknowledgementResult(
                run_id=snapshot.run_id,
                run_version=snapshot.active_run_version,
                state=snapshot.state.value,
                presentation_status=snapshot.presentation_status,
                duplicate=False,
                resume_required=True,
                observation=observation,
            )

        response = pending_response or {}
        stored_presentation = _json_object(snapshot.presentation)
        durable_event_ids = [
            str(item)
            for item in _json_list(stored_presentation.get("durable_event_ids"))
            if item
        ]
        fanout_existing = getattr(self.event_publisher, "fanout_existing", None)
        if durable_event_ids and callable(fanout_existing):
            # The repository already persisted the terminal events in the
            # same transaction as the run/conversation promotion. Only fan
            # those rows out to currently connected clients.
            fanout_existing_fn = cast(
                Callable[[str], Awaitable[object]], fanout_existing
            )
            for event_id in durable_event_ids:
                await fanout_existing_fn(event_id)
        else:
            # Test doubles and older repository compositions have no shared
            # event transaction. Keep the publishing fallback for them; the
            # production composition always supplies durable event IDs.
            if payload.status == "ready":
                await self.event_publisher.publish(
                    conversation_id=conversation_id,
                    run_id=payload.run_id,
                    run_version=payload.run_version,
                    type=RunEventType.PROGRESS,
                    payload={
                        "stage": RunProgressStage.COMPLETED.value,
                        "label": "Completed",
                    },
                )
                await self.event_publisher.publish(
                    conversation_id=conversation_id,
                    run_id=payload.run_id,
                    run_version=payload.run_version,
                    type=RunEventType.ASSISTANT_TEXT_COMPLETED,
                    payload={"content": response.get("assistant_message", "Map ready.")},
                )
                event_type = RunEventType.COMPLETED
                stored_requirements = _json_list(
                    stored_presentation.get("completion_requirements")
                )
                event_payload = {
                    **response,
                    "presentation_status": "ready",
                    "render_acknowledgment": acknowledgment,
                    "completion_requirements": CompletionEvaluator.acknowledge_requirements(
                        [
                            cast(dict[str, Any], item)
                            for item in stored_requirements
                            if isinstance(item, dict)
                        ],
                        acknowledgment,
                    ),
                }
            else:
                await self.event_publisher.publish(
                    conversation_id=conversation_id,
                    run_id=payload.run_id,
                    run_version=payload.run_version,
                    type=RunEventType.PROGRESS,
                    payload={
                        "stage": RunProgressStage.FAILED.value,
                        "label": "Map rendering failed",
                    },
                )
                event_type = RunEventType.ERROR
                event_payload = {
                    "code": payload.failure_code or "render_failed",
                    "message": "The prepared map could not be rendered; the previous map remains available.",
                    "presentation_status": "failed",
                    "render_acknowledgment": acknowledgment,
                }
            await self.event_publisher.publish(
                conversation_id=conversation_id,
                run_id=payload.run_id,
                run_version=payload.run_version,
                type=event_type,
                payload=event_payload,
            )
        return RenderAcknowledgementResult(
            run_id=snapshot.run_id,
            run_version=snapshot.active_run_version,
            state=snapshot.state.value,
            presentation_status=snapshot.presentation_status,
            duplicate=False,
            observation=observation,
        )

    # -------------------------------------------------------------------------
    def _observation_from_ack(
        self, payload: RealtimeRenderAckPayload
    ) -> RenderObservation:
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "map_session_id": payload.map_session_id,
                    "collection_revision": payload.collection_revision,
                    "checks": payload.checks,
                    "overlay_results": payload.overlay_results,
                },
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        ).hexdigest()
        failure_code = payload.failure_code or (
            "render_failed" if payload.status == "failed" else None
        )
        failure_summary = payload.failure_summary
        if payload.status == "failed" and not failure_summary:
            failed_checks = [
                key for key, value in payload.checks.items() if value is False
            ]
            failure_summary = (
                "Render acknowledgment failed"
                + (f" checks: {', '.join(failed_checks[:8])}." if failed_checks else ".")
            )
        return RenderObservation(
            map_session_id=payload.map_session_id,
            collection_revision=payload.collection_revision,
            attempt=1,
            status=payload.status,
            viewport_bounds=payload.viewport_bounds,
            checks=dict(payload.checks),
            overlay_results=[dict(item) for item in payload.overlay_results],
            failure_code=failure_code,
            failure_stage=payload.failure_stage,
            failure_summary=failure_summary,
            recovery="continue" if payload.status == "ready" else "revise_map",
            observed_at=utc_now().isoformat(),
        ).model_copy(update={"fingerprint": fingerprint})

    # -------------------------------------------------------------------------
    @staticmethod
    def _is_render_validation_rejection(message: str) -> bool:
        normalized = message.casefold()
        return normalized.startswith(
            (
                "required render checks failed:",
                "required overlay render checks failed:",
                "required rendered features are not visible:",
                "acknowledged viewport does not contain the prepared map.",
                "required map completion checks failed:",
            )
        )

    # -------------------------------------------------------------------------
    async def _publish_resume_observation(
        self,
        *,
        snapshot: Any,
        pending_response: dict[str, Any],
        observation: RenderObservation,
    ) -> None:
        """Publish a bounded render observation and the resume checkpoint."""

        payload = observation.model_dump(mode="json", exclude_none=True)
        payload["run_id"] = snapshot.run_id
        payload["run_version"] = snapshot.active_run_version
        await self.event_publisher.publish(
            conversation_id=snapshot.conversation_id,
            run_id=snapshot.run_id,
            run_version=snapshot.active_run_version,
            type=RunEventType.RENDER_OBSERVED,
            visibility=RunEventVisibility.USER,
            payload=payload,
        )
        await self.event_publisher.publish(
            conversation_id=snapshot.conversation_id,
            run_id=snapshot.run_id,
            run_version=snapshot.active_run_version,
            type=RunEventType.TRACE,
            visibility=RunEventVisibility.INTERNAL,
            payload=AgentTraceEvent(
                kind="render_observed",
                run_id=snapshot.run_id,
                run_version=snapshot.active_run_version,
                sequence=max(1, int(observation.attempt)),
                iteration=None,
                payload=payload,
            ).model_dump(mode="json"),
        )
        if observation.status == "failed":
            await self.event_publisher.publish(
                conversation_id=snapshot.conversation_id,
                run_id=snapshot.run_id,
                run_version=snapshot.active_run_version,
                type=RunEventType.PROGRESS,
                payload={
                    "stage": RunProgressStage.CORRECTING_RENDER.value,
                    "label": "Correcting the map after a render failure",
                    "failure_code": observation.failure_code,
                },
            )
        await self.event_publisher.publish(
            conversation_id=snapshot.conversation_id,
            run_id=snapshot.run_id,
            run_version=snapshot.active_run_version,
            type=RunEventType.TRACE,
            visibility=RunEventVisibility.INTERNAL,
            payload=AgentTraceEvent(
                kind="run_resumed",
                run_id=snapshot.run_id,
                run_version=snapshot.active_run_version,
                sequence=max(1, int(observation.attempt)),
                iteration=None,
                payload={
                    "reason": "render_observation",
                    "status": observation.status,
                    "attempt": observation.attempt,
                    "render_retry_exhausted": observation.recovery == "terminal",
                },
            ).model_dump(mode="json"),
        )
        checkpoint = _json_object(
            _json_object(pending_response.get("execution_trace")).get("checkpoint")
        )
        if not checkpoint:
            return
        checkpoint_event = AgentCheckpoint(
            run_id=snapshot.run_id,
            conversation_id=snapshot.conversation_id,
            run_version=snapshot.active_run_version,
            conversation_state={},
            run_state=checkpoint,
            state_hash=hashlib.sha256(
                json.dumps(
                    checkpoint, sort_keys=True, separators=(",", ":"), default=str
                ).encode("utf-8")
            ).hexdigest(),
            completed_call_fingerprints=list(
                _json_object(checkpoint.get("successful_fingerprints")).keys()
            )[-32:],
            completion_reason=None,
        )
        trace = AgentTraceEvent(
            kind="checkpoint",
            run_id=snapshot.run_id,
            run_version=snapshot.active_run_version,
            sequence=int(checkpoint.get("transitions") or 0),
            iteration=max(1, int(checkpoint.get("current_iteration") or 1)),
            payload=checkpoint_event.model_dump(mode="json"),
        )
        await self.event_publisher.publish(
            conversation_id=snapshot.conversation_id,
            run_id=snapshot.run_id,
            run_version=snapshot.active_run_version,
            type=RunEventType.CHECKPOINT,
            visibility=RunEventVisibility.INTERNAL,
            payload=trace.model_dump(mode="json"),
        )
