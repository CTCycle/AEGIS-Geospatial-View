from __future__ import annotations

import math

from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import uuid4

from server.contracts.events import (
    RunEventCreate,
    RunEventType,
    RunEventVisibility,
)
from server.contracts.runs import AgentRunSnapshot, AgentRunState
from server.repositories.agent_run_events import AgentRunEventRepository
from server.repositories.database.sqlite import SQLiteRepository
from sqlalchemy import or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from server.repositories.schemas.models import AgentRunRecord, ConversationRecord


###############################################################################
JsonObject = dict[str, Any]


###############################################################################
def _json_object(value: object) -> JsonObject:
    """Narrow a JSON value at a repository boundary."""
    if isinstance(value, dict):
        return cast(JsonObject, value)
    return {}


###############################################################################
def _json_list(value: object) -> list[Any]:
    if isinstance(value, list):
        return cast(list[Any], value)
    return []


###############################################################################
class AgentRunRepository:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        database: SQLiteRepository,
        *,
        event_repository: AgentRunEventRepository | None = None,
    ) -> None:
        self._session_factory = database.session
        self._event_repository = event_repository

    # -------------------------------------------------------------------------
    def create_run(
        self,
        conversation_id: str,
        original_request: str,
        aggregated_request: str,
        client_request_id: str | None = None,
        request_timezone: str | None = None,
    ) -> AgentRunSnapshot:
        snapshot, _created = self.create_or_get_run(
            conversation_id,
            original_request,
            aggregated_request,
            client_request_id=client_request_id,
            request_timezone=request_timezone,
        )
        return snapshot

    # -------------------------------------------------------------------------
    def create_or_get_run(
        self,
        conversation_id: str,
        original_request: str,
        aggregated_request: str,
        *,
        client_request_id: str | None = None,
        request_timezone: str | None = None,
    ) -> tuple[AgentRunSnapshot, bool]:
        with self._session_factory() as session:
            # Serialize active-run creation with render acknowledgment and
            # cancellation on SQLite.  Without taking the write lock before
            # the first read, two concurrent requests could both observe an
            # apparently free conversation and race while superseding a
            # pending presentation.
            session.execute(text("BEGIN IMMEDIATE"))
            conversation = session.get(ConversationRecord, conversation_id)
            if conversation is None:
                raise ValueError("Conversation not found.")
            if client_request_id is not None:
                existing = session.scalar(
                    select(AgentRunRecord).where(
                        AgentRunRecord.conversation_id == conversation_id,
                        AgentRunRecord.client_request_id == client_request_id,
                    )
                )
                if existing is not None:
                    return self._to_snapshot(existing), False
            active = session.scalar(
                select(AgentRunRecord.id).where(
                    AgentRunRecord.conversation_id == conversation_id,
                    AgentRunRecord.active_slot == 1,
                )
            )
            if active is not None:
                raise ValueError("Conversation already has an active run.")
            # A browser candidate has released the execution slot but still
            # owns the conversation's pending presentation. A genuinely new
            # request supersedes it in the same transaction so an old render
            # acknowledgment can never promote stale geography later.
            pending = (
                session.execute(
                    select(AgentRunRecord).where(
                        AgentRunRecord.conversation_id == conversation_id,
                        AgentRunRecord.state == AgentRunState.AWAITING_RENDER.value,
                    )
                )
                .scalars()
                .all()
            )
            now = datetime.now(UTC)
            for previous in pending:
                previous.state = AgentRunState.CANCELLED.value
                previous.active_slot = None
                previous.cancel_requested_at = previous.cancel_requested_at or now
                previous.completed_at = previous.completed_at or now
                previous.error_code = "superseded"
                previous.error_message = "A newer request replaced the pending map."
                previous.presentation_status = "not_required"
                previous.presentation_json = None
            record = AgentRunRecord(
                id=f"run_{uuid4().hex}",
                conversation_id=conversation_id,
                client_request_id=client_request_id,
                request_timezone=request_timezone,
                original_request=original_request,
                aggregated_request=aggregated_request,
                active_run_version=1,
                state=AgentRunState.PENDING.value,
                active_slot=1,
            )
            session.add(record)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                if client_request_id is not None:
                    existing = session.scalar(
                        select(AgentRunRecord).where(
                            AgentRunRecord.conversation_id == conversation_id,
                            AgentRunRecord.client_request_id == client_request_id,
                        )
                    )
                    if existing is not None:
                        return self._to_snapshot(existing), False
                raise ValueError("Conversation already has an active run.") from exc
            session.refresh(record)
            return self._to_snapshot(record), True

    # -------------------------------------------------------------------------
    def get_run(self, run_id: str) -> AgentRunSnapshot | None:
        with self._session_factory() as session:
            record = session.get(AgentRunRecord, run_id)
            return self._to_snapshot(record) if record is not None else None

    # -------------------------------------------------------------------------
    def get_active_run_for_conversation(
        self,
        conversation_id: str,
    ) -> AgentRunSnapshot | None:
        with self._session_factory() as session:
            if session.get(ConversationRecord, conversation_id) is None:
                return None
            record = session.scalar(
                select(AgentRunRecord).where(
                    AgentRunRecord.conversation_id == conversation_id,
                    or_(
                        AgentRunRecord.active_slot == 1,
                        AgentRunRecord.state == AgentRunState.AWAITING_RENDER.value,
                    ),
                )
            )
            return self._to_snapshot(record) if record is not None else None

    # -------------------------------------------------------------------------
    def set_state(self, run_id: str, state: AgentRunState) -> AgentRunSnapshot:
        with self._session_factory() as session:
            record = self._require_run(session, run_id)
            record.state = state.value
            session.commit()
            session.refresh(record)
            return self._to_snapshot(record)

    # -------------------------------------------------------------------------
    def request_cancel(self, run_id: str) -> AgentRunSnapshot:
        with self._session_factory() as session:
            record = self._require_run(session, run_id)
            record.state = AgentRunState.CANCELLED.value
            record.active_slot = None
            record.cancel_requested_at = record.cancel_requested_at or datetime.now(UTC)
            record.completed_at = record.completed_at or datetime.now(UTC)
            session.commit()
            session.refresh(record)
            return self._to_snapshot(record)

    # -------------------------------------------------------------------------
    def request_cancel_once(self, run_id: str) -> tuple[AgentRunSnapshot, bool]:
        """Transition a non-terminal run to cancelled at most once."""
        with self._session_factory() as session:
            now = datetime.now(UTC)
            updated = cast(
                CursorResult[Any],
                session.execute(
                    update(AgentRunRecord)
                    .where(
                        AgentRunRecord.id == run_id,
                        or_(
                            AgentRunRecord.active_slot == 1,
                            AgentRunRecord.state == AgentRunState.AWAITING_RENDER.value,
                        ),
                        AgentRunRecord.state.notin_(
                            [
                                AgentRunState.COMPLETED.value,
                                AgentRunState.FAILED.value,
                                AgentRunState.CANCELLED.value,
                            ]
                        ),
                    )
                    .values(
                        state=AgentRunState.CANCELLED.value,
                        active_slot=None,
                        cancel_requested_at=now,
                        completed_at=now,
                    )
                ),
            )
            session.commit()
            record = self._require_run(session, run_id)
            return self._to_snapshot(record), int(updated.rowcount or 0) == 1

    # -------------------------------------------------------------------------
    def mark_completed_if_current(
        self, run_id: str, expected_run_version: int
    ) -> tuple[AgentRunSnapshot, bool]:
        """Complete only the still-current, non-cancelled run version."""
        with self._session_factory() as session:
            updated = cast(
                CursorResult[Any],
                session.execute(
                    update(AgentRunRecord)
                    .where(
                        AgentRunRecord.id == run_id,
                        AgentRunRecord.active_run_version == expected_run_version,
                        AgentRunRecord.active_slot == 1,
                        AgentRunRecord.cancel_requested_at.is_(None),
                        AgentRunRecord.state.notin_(
                            [
                                AgentRunState.COMPLETED.value,
                                AgentRunState.FAILED.value,
                                AgentRunState.CANCELLED.value,
                            ]
                        ),
                    )
                    .values(
                        state=AgentRunState.COMPLETED.value,
                        active_slot=None,
                        completed_at=datetime.now(UTC),
                    )
                ),
            )
            session.commit()
            record = self._require_run(session, run_id)
            return self._to_snapshot(record), int(updated.rowcount) == 1

    # -------------------------------------------------------------------------
    def prepare_render(
        self,
        run_id: str,
        expected_run_version: int,
        presentation: dict[str, Any],
    ) -> tuple[AgentRunSnapshot, bool]:
        """Move a valid map candidate into the durable awaiting-render state."""
        with self._session_factory() as session:
            updated = cast(
                CursorResult[Any],
                session.execute(
                    update(AgentRunRecord)
                    .where(
                        AgentRunRecord.id == run_id,
                        AgentRunRecord.active_run_version == expected_run_version,
                        AgentRunRecord.active_slot == 1,
                        AgentRunRecord.cancel_requested_at.is_(None),
                        AgentRunRecord.state.notin_(
                            [
                                AgentRunState.COMPLETED.value,
                                AgentRunState.FAILED.value,
                                AgentRunState.CANCELLED.value,
                            ]
                        ),
                    )
                    .values(
                        state=AgentRunState.AWAITING_RENDER.value,
                        active_slot=None,
                        presentation_status="pending",
                        presentation_json=presentation,
                    )
                ),
            )
            session.commit()
            record = self._require_run(session, run_id)
            return self._to_snapshot(record), int(updated.rowcount or 0) == 1

    # -------------------------------------------------------------------------
    def acknowledge_render(
        self,
        *,
        conversation_id: str,
        run_id: str,
        run_version: int,
        map_session_id: str,
        collection_revision: int,
        status: str,
        acknowledgment: dict[str, Any],
    ) -> tuple[AgentRunSnapshot, bool, dict[str, Any] | None]:
        """Accept one browser acknowledgment and promote its map atomically."""
        with self._session_factory() as session:
            # SQLite does not implement SELECT ... FOR UPDATE.  Start an
            # immediate write transaction before reading the pending row so
            # cancellation/supersession and duplicate acknowledgments have a
            # single serializable winner on the application database.
            session.execute(text("BEGIN IMMEDIATE"))
            run = session.scalar(
                select(AgentRunRecord)
                .where(AgentRunRecord.id == run_id)
                .with_for_update()
            )
            if run is None or run.conversation_id != conversation_id:
                raise ValueError("Run not found.")
            presentation = _json_object(run.presentation_json)
            expected_session = str(presentation.get("map_session_id") or "")
            expected_revision = presentation.get("collection_revision")
            if (
                run.active_run_version != run_version
                or expected_session != map_session_id
                or expected_revision != collection_revision
            ):
                raise ValueError("Render acknowledgment does not match the prepared map.")
            if run.presentation_status in {"ready", "failed"}:
                previous = presentation.get("acknowledgment")
                if previous == acknowledgment:
                    return self._to_snapshot(run), True, presentation
                raise ValueError("A different render acknowledgment was already accepted.")
            if run.presentation_status != "pending" or run.state != AgentRunState.AWAITING_RENDER.value:
                raise ValueError("Run is not awaiting map rendering.")

            pending_response_value: object = presentation.get("pending_response")
            if not isinstance(pending_response_value, dict):
                raise ValueError("Prepared map response is missing.")
            pending_response = cast(JsonObject, pending_response_value)
            if status == "ready":
                if not isinstance(acknowledgment.get("viewport_bounds"), list):
                    raise ValueError(
                        "A ready render acknowledgment must include viewport bounds."
                    )
                required_checks = _json_object(presentation.get("required_render_checks"))
                checks = _json_object(acknowledgment.get("checks"))
                missing_checks = [
                    str(name)
                    for name, required in required_checks.items()
                    if required is True
                    and checks.get(name) is not True
                ]
                if missing_checks:
                    raise ValueError(
                        "Required render checks failed: " + ", ".join(missing_checks)
                    )
                required_overlay_ids = [
                    str(item) for item in _json_list(presentation.get("required_overlay_ids"))
                ]
                if required_overlay_ids:
                    overlay_results = [
                        cast(JsonObject, item)
                        for item in _json_list(acknowledgment.get("overlay_results"))
                        if isinstance(item, dict)
                    ]
                    by_id = {
                        str(item.get("overlay_id")): item
                        for item in overlay_results
                        if item.get("overlay_id")
                    }
                    candidate_instances = self._candidate_overlay_instances(
                        pending_response.get("map_session")
                    )
                    required_capability_instances: dict[str, list[dict[str, Any]]] = {}
                    for required_id in required_overlay_ids:
                        required_instance = candidate_instances.get(str(required_id))
                        if required_instance is None:
                            continue
                        required_capability = str(
                            required_instance.get("capability_id") or ""
                        )
                        if required_capability:
                            required_capability_instances.setdefault(
                                required_capability, []
                            ).append(required_instance)
                    missing_overlays: list[str] = []
                    for raw_id in required_overlay_ids:
                        overlay_id = str(raw_id)
                        result = by_id.get(overlay_id)
                        if result is None:
                            # Clients may report the stable capability ID. Accept
                            # that alias only when it maps to one required
                            # instance and the evidence declares the alias.
                            instance = candidate_instances.get(overlay_id)
                            capability_id = (
                                str(instance.get("capability_id") or "")
                                if instance is not None
                                else ""
                            )
                            aliases = (
                                [
                                    candidate
                                    for candidate in overlay_results
                                    if candidate.get("overlay_id") == capability_id
                                    or candidate.get("capability_id") == capability_id
                                ]
                                if len(required_capability_instances.get(capability_id, []))
                                == 1
                                else []
                            )
                            result = aliases[0] if len(aliases) == 1 else None
                        if result is None or any(
                            result.get(name) is not True
                            for name in ("source_present", "layer_present", "loaded")
                        ):
                            missing_overlays.append(overlay_id)
                        elif result.get("visibility_matches") is not True:
                            missing_overlays.append(overlay_id)
                    if missing_overlays:
                        raise ValueError(
                            "Required overlay render checks failed: "
                            + ", ".join(missing_overlays)
                        )
                    # A successfully loaded source/layer can still render no
                    # features because the candidate was empty, scoped to the
                    # wrong area, or supplied malformed GeoJSON. When the
                    # prepared candidate includes concrete vector features,
                    # require the browser to report at least one visible
                    # feature. URL-backed/vector-tile and valid-empty results
                    # remain governed by their source/layer checks.
                    pending_instances = self._candidate_overlay_instances(
                        pending_response.get("map_session")
                    )
                    missing_features: list[str] = []
                    for overlay_id in required_overlay_ids:
                        if not self._candidate_requires_visible_features(
                            pending_instances.get(str(overlay_id))
                        ):
                            continue
                        result = by_id.get(str(overlay_id))
                        if result is None:
                            instance = pending_instances.get(str(overlay_id))
                            capability_id = str(instance.get("capability_id") or "") if instance else ""
                            aliases = [
                                candidate
                                for candidate in overlay_results
                                if candidate.get("overlay_id") == capability_id
                                or candidate.get("capability_id") == capability_id
                            ]
                            result = aliases[0] if len(aliases) == 1 else None
                        rendered_count = result.get("rendered_feature_count") if result else None
                        instance = pending_instances.get(str(overlay_id))
                        if instance is not None and instance.get("visible") is False:
                            continue
                        if not isinstance(rendered_count, int) or rendered_count <= 0:
                            missing_features.append(str(overlay_id))
                    if missing_features:
                        raise ValueError(
                            "Required rendered features are not visible: "
                            + ", ".join(missing_features)
                        )
                pending_map = pending_response.get("map_session")
                expected_bounds = self._candidate_bounds(pending_map)
                viewport_bounds = acknowledgment.get("viewport_bounds")
                if expected_bounds is not None and viewport_bounds is not None:
                    if not self._bounds_intersect(expected_bounds, viewport_bounds):
                        raise ValueError(
                            "Acknowledged viewport does not contain the prepared map."
                        )
                completion_requirements = _json_list(
                    presentation.get("completion_requirements")
                )
                if completion_requirements:
                    blocked_requirements = [
                        str(cast(JsonObject, item).get("name") or "required output")
                        for item in completion_requirements
                        if isinstance(item, dict)
                        and cast(JsonObject, item).get("required") is True
                        and cast(JsonObject, item).get("name")
                        not in {
                            "map_state_committed",
                            "viewport_contains_results",
                            "final_response_ready",
                        }
                        and cast(JsonObject, item).get("status")
                        not in {"satisfied", "not_applicable"}
                    ]
                    if blocked_requirements:
                        raise ValueError(
                            "Required map completion checks failed: "
                            + ", ".join(blocked_requirements)
                        )
            if status not in {"ready", "failed"}:
                raise ValueError("Unsupported render acknowledgment status.")
            if status == "ready":
                response_memory = _json_object(pending_response.get("memory_snapshot"))
                task_snapshot = _json_object(pending_response.get("task_snapshot"))
                conversation = session.get(ConversationRecord, conversation_id)
                if conversation is None:
                    raise ValueError("Conversation not found.")
                candidate_map = pending_response.get("map_session")
                promoted_task_snapshot = dict(
                    task_snapshot
                    if task_snapshot
                    else _json_object(conversation.task_snapshot)
                )
                promoted_memory = dict(
                    response_memory
                    if response_memory
                    else _json_object(conversation.memory_snapshot)
                )
                if isinstance(candidate_map, dict):
                    promoted_task_snapshot["active_map_session"] = candidate_map
                    promoted_memory["active_visualization"] = candidate_map
                conversation.task_snapshot = promoted_task_snapshot
                conversation.memory_snapshot = promoted_memory
                conversation.context_revision += 1
                pending_response["context_revision"] = conversation.context_revision
                run.state = AgentRunState.COMPLETED.value
                run.completed_at = datetime.now(UTC)
                run.presentation_status = "ready"
                updated_presentation: JsonObject = {
                    **presentation,
                    "acknowledgment": acknowledgment,
                }
                stored_requirements = _json_list(
                    presentation.get("completion_requirements")
                )
                updated_requirements: list[dict[str, Any]] = []
                if stored_requirements:
                    from server.services.agent.completion import CompletionEvaluator

                    updated_requirements = CompletionEvaluator.acknowledge_requirements(
                        [
                            cast(JsonObject, item)
                            for item in stored_requirements
                            if isinstance(item, dict)
                        ],
                        acknowledgment,
                    )
                    blocked_after_ack = [
                        str(item.get("name") or "required output")
                        for item in updated_requirements
                        if item.get("required") is True
                        and item.get("status") not in {"satisfied", "not_applicable"}
                    ]
                    if blocked_after_ack:
                        raise ValueError(
                            "Required map completion checks failed: "
                            + ", ".join(blocked_after_ack)
                        )
                    updated_presentation["completion_requirements"] = updated_requirements
                durable_event_creates = [
                    RunEventCreate(
                        conversation_id=conversation_id,
                        run_id=run_id,
                        run_version=run_version,
                        type=RunEventType.PROGRESS,
                        visibility=RunEventVisibility.USER,
                        payload={
                            "stage": "completed",
                            "label": "Completed",
                        },
                    ),
                    RunEventCreate(
                        conversation_id=conversation_id,
                        run_id=run_id,
                        run_version=run_version,
                        type=RunEventType.ASSISTANT_TEXT_COMPLETED,
                        visibility=RunEventVisibility.USER,
                        payload={
                            "content": pending_response.get(
                                "assistant_message", "Map ready."
                            ),
                            "operation": pending_response.get("operation"),
                        },
                    ),
                    RunEventCreate(
                        conversation_id=conversation_id,
                        run_id=run_id,
                        run_version=run_version,
                        type=RunEventType.COMPLETED,
                        visibility=RunEventVisibility.USER,
                        payload={
                            **pending_response,
                            "state": "completed",
                            "presentation_status": "ready",
                            "render_acknowledgment": acknowledgment,
                            "completion_requirements": updated_requirements,
                        },
                    ),
                ]
            elif status == "failed":
                run.state = AgentRunState.FAILED.value
                run.completed_at = datetime.now(UTC)
                run.error_code = str(acknowledgment.get("failure_code") or "render_failed")
                run.error_message = "The prepared map could not be rendered."
                run.presentation_status = "failed"
                updated_presentation = {
                    **presentation,
                    "acknowledgment": acknowledgment,
                }
                durable_event_creates = [
                    RunEventCreate(
                        conversation_id=conversation_id,
                        run_id=run_id,
                        run_version=run_version,
                        type=RunEventType.PROGRESS,
                        visibility=RunEventVisibility.USER,
                        payload={
                            "stage": "failed",
                            "label": "Map rendering failed",
                        },
                    ),
                    RunEventCreate(
                        conversation_id=conversation_id,
                        run_id=run_id,
                        run_version=run_version,
                        type=RunEventType.ERROR,
                        visibility=RunEventVisibility.USER,
                        payload={
                            "code": run.error_code,
                            "message": run.error_message,
                            "presentation_status": "failed",
                            "render_acknowledgment": acknowledgment,
                        },
                    ),
                ]
            else:
                raise ValueError("Unsupported render acknowledgment status.")
            run.active_slot = None
            if self._event_repository is not None:
                event_ids: list[str] = []
                for event_create in durable_event_creates:
                    event = self._event_repository.append_event_in_session(
                        session, event_create
                    )
                    event_ids.append(event.event_id)
                updated_presentation["durable_event_ids"] = event_ids
            run.presentation_json = updated_presentation
            session.commit()
            session.refresh(run)
            return self._to_snapshot(run), False, pending_response

    # -------------------------------------------------------------------------
    @staticmethod
    def _candidate_bounds(value: object) -> list[float] | None:
        if not isinstance(value, dict):
            return None
        value_object: JsonObject = cast(JsonObject, value)
        bounds_value: object = value_object.get("bounds")
        if not isinstance(bounds_value, list):
            viewport = _json_object(value_object.get("viewport"))
            bounds_value = viewport.get("bbox")
        if not isinstance(bounds_value, list):
            return None
        bounds_items = cast(list[Any], bounds_value)
        if len(bounds_items) != 4:
            return None
        try:
            normalized = [float(item) for item in bounds_items]
        except (TypeError, ValueError):
            return None
        west, south, east, north = normalized
        if not all(math.isfinite(item) for item in normalized):
            return None
        if not (-180 <= west <= 180 and -180 <= east <= 180):
            return None
        if west > east and (west < 150 or east > -150):
            return None
        if not (-90 <= south <= north <= 90):
            return None
        return normalized

    # -------------------------------------------------------------------------
    @staticmethod
    def _candidate_overlay_instances(
        value: object,
    ) -> dict[str, dict[str, Any]]:
        if not isinstance(value, dict):
            return {}
        value_object: JsonObject = cast(JsonObject, value)
        collection = _json_object(value_object.get("overlay_collection"))
        instances = _json_list(collection.get("instances"))
        return {
            str(item.get("instance_id")): item
            for item in (cast(JsonObject, item) for item in instances if isinstance(item, dict))
            if item.get("instance_id")
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def _candidate_requires_visible_features(
        instance: dict[str, Any] | None,
    ) -> bool:
        if instance is None:
            return False
        mode = str(instance.get("rendering_mode") or "").casefold()
        if mode in {"metadata-only", "metadata_only"}:
            return False
        descriptor = _json_object(instance.get("descriptor"))
        result_type = str(
            descriptor.get("result_type") or descriptor.get("resultType") or ""
        ).casefold()
        if result_type in {"metadata", "empty", "valid_empty"}:
            return False
        data = _json_object(descriptor.get("data"))
        features = data.get("features")
        return isinstance(features, list) and len(cast(list[Any], features)) > 0

    # -------------------------------------------------------------------------
    @staticmethod
    def _bounds_intersect(left: list[float], right: object) -> bool:
        if not isinstance(right, list):
            return False
        right_items = cast(list[Any], right)
        if len(right_items) != 4:
            return False
        try:
            other = [float(item) for item in right_items]
        except (TypeError, ValueError):
            return False
        l_west, l_south, l_east, l_north = left
        r_west, r_south, r_east, r_north = other
        if l_south > l_north or r_south > r_north:
            return False
        if (l_west > l_east and (l_west < 150 or l_east > -150)) or (
            r_west > r_east and (r_west < 150 or r_east > -150)
        ):
            return False
        if l_north < r_south or r_north < l_south:
            return False

        def longitude_intervals(west: float, east: float) -> list[tuple[float, float]]:
            if west <= east:
                return [(west, east)]
            # An explicit antimeridian crossing is the union of the two
            # ordinary EPSG:4326 intervals at the world edge.
            return [(-180.0, east), (west, 180.0)]

        return any(
            left_west <= right_east and right_west <= left_east
            for left_west, left_east in longitude_intervals(l_west, l_east)
            for right_west, right_east in longitude_intervals(r_west, r_east)
        )

    # -------------------------------------------------------------------------
    def mark_failed_if_current(
        self, run_id: str, expected_run_version: int, code: str, message: str
    ) -> tuple[AgentRunSnapshot, bool]:
        """Fail only the still-current, non-cancelled run version."""
        with self._session_factory() as session:
            updated = cast(
                CursorResult[Any],
                session.execute(
                    update(AgentRunRecord)
                    .where(
                        AgentRunRecord.id == run_id,
                        AgentRunRecord.active_run_version == expected_run_version,
                        AgentRunRecord.active_slot == 1,
                        AgentRunRecord.cancel_requested_at.is_(None),
                        AgentRunRecord.state.notin_(
                            [
                                AgentRunState.COMPLETED.value,
                                AgentRunState.FAILED.value,
                                AgentRunState.CANCELLED.value,
                            ]
                        ),
                    )
                    .values(
                        state=AgentRunState.FAILED.value,
                        active_slot=None,
                        error_code=code,
                        error_message=message,
                        completed_at=datetime.now(UTC),
                    )
                ),
            )
            session.commit()
            record = self._require_run(session, run_id)
            return self._to_snapshot(record), int(updated.rowcount) == 1

    # -------------------------------------------------------------------------
    def update_aggregated_request(
        self,
        run_id: str,
        aggregated_request: str,
        next_version: int,
    ) -> AgentRunSnapshot:
        with self._session_factory() as session:
            record = self._require_run(session, run_id)
            record.aggregated_request = aggregated_request
            record.active_run_version = next_version
            record.state = AgentRunState.UPDATING.value
            session.commit()
            session.refresh(record)
            return self._to_snapshot(record)

    # -------------------------------------------------------------------------
    def mark_started(self, run_id: str) -> AgentRunSnapshot:
        with self._session_factory() as session:
            record = self._require_run(session, run_id)
            record.state = AgentRunState.RUNNING.value
            record.started_at = record.started_at or datetime.now(UTC)
            record.observed_by_worker_version = record.active_run_version
            session.commit()
            session.refresh(record)
            return self._to_snapshot(record)

    # -------------------------------------------------------------------------
    def mark_started_if_current(
        self, run_id: str, expected_run_version: int
    ) -> tuple[AgentRunSnapshot, bool]:
        """Start only the still-current, non-cancelled run version."""
        with self._session_factory() as session:
            updated = cast(
                CursorResult[Any],
                session.execute(
                    update(AgentRunRecord)
                    .where(
                        AgentRunRecord.id == run_id,
                        AgentRunRecord.active_run_version == expected_run_version,
                        AgentRunRecord.active_slot == 1,
                        AgentRunRecord.cancel_requested_at.is_(None),
                        AgentRunRecord.state.notin_(
                            [
                                AgentRunState.COMPLETED.value,
                                AgentRunState.FAILED.value,
                                AgentRunState.CANCELLED.value,
                            ]
                        ),
                    )
                    .values(
                        state=AgentRunState.RUNNING.value,
                        started_at=datetime.now(UTC),
                        observed_by_worker_version=expected_run_version,
                    )
                ),
            )
            session.commit()
            record = self._require_run(session, run_id)
            return self._to_snapshot(record), int(updated.rowcount or 0) == 1

    # -------------------------------------------------------------------------
    def mark_completed(self, run_id: str) -> AgentRunSnapshot:
        with self._session_factory() as session:
            record = self._require_run(session, run_id)
            record.state = AgentRunState.COMPLETED.value
            record.active_slot = None
            record.completed_at = datetime.now(UTC)
            session.commit()
            session.refresh(record)
            return self._to_snapshot(record)

    # -------------------------------------------------------------------------
    def mark_failed(self, run_id: str, code: str, message: str) -> AgentRunSnapshot:
        with self._session_factory() as session:
            record = self._require_run(session, run_id)
            record.state = AgentRunState.FAILED.value
            record.active_slot = None
            record.error_code = code
            record.error_message = message
            record.completed_at = datetime.now(UTC)
            session.commit()
            session.refresh(record)
            return self._to_snapshot(record)

    # -------------------------------------------------------------------------
    @staticmethod
    def _require_run(session: Session, run_id: str) -> AgentRunRecord:
        record = session.get(AgentRunRecord, run_id)
        if record is None:
            raise ValueError("Run not found.")
        return record

    # -------------------------------------------------------------------------
    @staticmethod
    def _to_snapshot(record: AgentRunRecord) -> AgentRunSnapshot:
        return AgentRunSnapshot(
            conversation_id=record.conversation_id,
            run_id=record.id,
            original_request=record.original_request,
            aggregated_request=record.aggregated_request,
            active_run_version=record.active_run_version,
            state=AgentRunState(record.state),
            created_at=record.created_at,
            request_timezone=record.request_timezone,
            started_at=record.started_at,
            completed_at=record.completed_at,
            cancel_requested_at=record.cancel_requested_at,
            error_code=record.error_code,
            error_message=record.error_message,
            presentation_status=cast(
                Literal["not_required", "pending", "ready", "failed"],
                record.presentation_status
                if record.presentation_status
                in {"not_required", "pending", "ready", "failed"}
                else "not_required",
            ),
            presentation=record.presentation_json,
        )
