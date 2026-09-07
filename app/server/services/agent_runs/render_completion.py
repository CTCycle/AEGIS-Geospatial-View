"""Durable map presentation handshake between the backend and MapLibre."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

from server.contracts.events import RunEventType, RunProgressStage
from server.domain.realtime import RealtimeRenderAckPayload
from server.contracts.geospatial import MapSession
from server.domain.agent.interpretation import CanonicalRequestInterpretation
from server.repositories.agent_runs import AgentRunRepository
from server.services.agent.completion import CompletionEvaluator
from server.services.agent_runs.events import RunEventPublisher


###############################################################################
class RenderAcknowledgementError(ValueError):
    """Raised when browser evidence cannot be applied to the prepared run."""


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


###############################################################################
class RenderCompletionService:
    """Prepare candidates and atomically promote acknowledged map sessions."""

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        run_repository: AgentRunRepository,
        event_publisher: RunEventPublisher,
    ) -> None:
        self.run_repository = run_repository
        self.event_publisher = event_publisher

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
        canonical_raw = response_payload.get("canonical_request")
        canonical_request = (
            CanonicalRequestInterpretation.model_validate(canonical_raw)
            if isinstance(canonical_raw, dict)
            else None
        )
        render_requirements = CompletionEvaluator.candidate_requirements(
            canonical_request, candidate_model
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
        try:
            snapshot, duplicate, pending_response = self.run_repository.acknowledge_render(
                conversation_id=conversation_id,
                run_id=payload.run_id,
                run_version=payload.run_version,
                map_session_id=payload.map_session_id,
                collection_revision=payload.collection_revision,
                status=payload.status,
                acknowledgment=acknowledgment,
            )
        except ValueError as exc:
            raise RenderAcknowledgementError(str(exc)) from exc
        if duplicate:
            return RenderAcknowledgementResult(
                run_id=snapshot.run_id,
                run_version=snapshot.active_run_version,
                state=snapshot.state.value,
                presentation_status=snapshot.presentation_status,
                duplicate=True,
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
        )
