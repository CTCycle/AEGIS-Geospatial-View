from __future__ import annotations

import base64
import json
import math
import re

from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast
from uuid import uuid4

from server.contracts.events import (
    RunEventCreate,
    RunEventType,
    RunEventVisibility,
)
from server.contracts.runs import AgentRunSnapshot, AgentRunState
from server.contracts.geospatial import MapSession
from server.domain.agent.capability_route import AgentTaskState
from server.domain.agent.conversation import ConversationState
from server.repositories.agent_run_events import AgentRunEventRepository
from server.repositories.database.sqlite import SQLiteRepository
from sqlalchemy import and_, case, func, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from server.repositories.schemas.models import (
    AgentRunEventRecord,
    AgentRunRecord,
    ChatMessageRecord,
    ConversationRecord,
)


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


def _finalize_pending_presentation(
    value: object,
    *,
    status: str,
    error_code: str | None = None,
    force: bool = False,
) -> JsonObject | None:
    """Close an in-flight presentation without retaining its pending response."""

    if not isinstance(value, dict):
        return None
    presentation = dict(cast(JsonObject, value))
    if not force and str(presentation.get("status") or "").casefold() not in {
        "pending",
        "resuming",
    }:
        return presentation
    presentation["status"] = status
    if error_code:
        presentation["error_code"] = error_code
    presentation.pop("pending_response", None)
    return presentation


###############################################################################
class AgentRunRepository:

    MAX_PAGE_LIMIT = 50
    MAX_TRACE_LIMIT = 200
    MAX_QUERY_CHARS = 300

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
                previous.render_prepared_at = None
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
            snapshot = self._to_snapshot(record) if record is not None else None
        return self._attach_task_state(snapshot)

    # -------------------------------------------------------------------------
    def get_task_state(
        self,
        run_id: str,
        *,
        run_version: int | None = None,
    ) -> dict[str, Any] | None:
        """Return the newest typed task-state checkpoint for one run.

        Task state is intentionally kept in the existing event/evidence
        storage boundary rather than adding a second run table.  Completed
        responses and native checkpoints both carry the same bounded task
        ledger, so this reader accepts either envelope while never exposing
        provider messages or hidden reasoning.
        """

        with self._session_factory() as session:
            filters: list[Any] = [AgentRunEventRecord.run_id == str(run_id)]
            if run_version is not None:
                filters.append(AgentRunEventRecord.run_version == run_version)
            rows = list(
                session.scalars(
                    select(AgentRunEventRecord)
                    .where(*filters)
                    .order_by(AgentRunEventRecord.sequence.desc())
                    .limit(256)
                ).all()
            )
        for row in rows:
            payload = _json_object(row.payload_json)
            candidate = _task_state_from_payload(payload)
            if candidate is not None:
                return candidate
        return None

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
            snapshot = self._to_snapshot(record) if record is not None else None
        return self._attach_task_state(snapshot)

    # -------------------------------------------------------------------------
    def _attach_task_state(
        self, snapshot: AgentRunSnapshot | None
    ) -> AgentRunSnapshot | None:
        if snapshot is None:
            return None
        raw = self.get_task_state(
            snapshot.run_id,
            run_version=snapshot.active_run_version,
        )
        if not isinstance(raw, dict):
            return snapshot
        try:
            typed = AgentTaskState.model_validate(raw)
        except (TypeError, ValueError):
            return snapshot
        return snapshot.model_copy(
            update={
                "current_iteration": typed.current_iteration,
                "task_state": typed,
            }
        )

    # -------------------------------------------------------------------------
    def list_resumable_runs(self) -> list[AgentRunSnapshot]:
        """Return active native runs that survived a process interruption."""

        with self._session_factory() as session:
            records = (
                session.execute(
                    select(AgentRunRecord)
                    .where(
                        AgentRunRecord.active_slot == 1,
                        AgentRunRecord.cancel_requested_at.is_(None),
                        AgentRunRecord.state.in_(
                            [
                                AgentRunState.PENDING.value,
                                AgentRunState.RUNNING.value,
                                AgentRunState.UPDATING.value,
                            ]
                        ),
                    )
                    .order_by(AgentRunRecord.created_at.asc())
                )
                .scalars()
                .all()
            )
        return [
            attached
            for record in records
            if (attached := self._attach_task_state(self._to_snapshot(record)))
            is not None
        ]

    # -------------------------------------------------------------------------
    def list_runs_for_conversation(
        self,
        conversation_id: str,
        *,
        query: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
        include_terminal: bool = True,
    ) -> dict[str, Any]:
        """Return bounded run summaries for one conversation.

        Runs are sorted newest-first by ``created_at`` and ``id``.  The
        cursor is an opaque keyset cursor, so adding a newer run does not
        duplicate or skip entries already paged through.  Search is scoped to
        the run's original and aggregated request text.
        """

        normalized_conversation_id = str(conversation_id).strip()
        if not normalized_conversation_id:
            raise ValueError("Conversation id is required.")
        bounded_limit = max(1, min(int(limit), self.MAX_PAGE_LIMIT))
        normalized_query = " ".join(str(query or "").split())
        if len(normalized_query) > self.MAX_QUERY_CHARS:
            normalized_query = normalized_query[: self.MAX_QUERY_CHARS]
        sort_cursor = _decode_run_cursor(cursor)

        with self._session_factory() as session:
            if session.get(ConversationRecord, normalized_conversation_id) is None:
                raise ValueError("Conversation not found.")
            filters = [
                AgentRunRecord.conversation_id == normalized_conversation_id
            ]
            if not include_terminal:
                filters.append(
                    AgentRunRecord.state.notin_(
                        [
                            AgentRunState.COMPLETED.value,
                            AgentRunState.FAILED.value,
                            AgentRunState.CANCELLED.value,
                        ]
                    )
                )
            if normalized_query:
                pattern = _sqlite_contains_pattern(normalized_query)
                filters.append(
                    or_(
                        func.lower(AgentRunRecord.original_request).like(
                            pattern, escape="\\"
                        ),
                        func.lower(AgentRunRecord.aggregated_request).like(
                            pattern, escape="\\"
                        ),
                    )
                )
            all_filters = list(filters)
            if sort_cursor is not None:
                cursor_time, cursor_id = sort_cursor
                filters.append(
                    or_(
                        AgentRunRecord.created_at < cursor_time,
                        and_(
                            AgentRunRecord.created_at == cursor_time,
                            AgentRunRecord.id < cursor_id,
                        ),
                    )
                )
            total = int(
                session.scalar(
                    select(func.count())
                    .select_from(AgentRunRecord)
                    .where(*all_filters)
                )
                or 0
            )
            rows = list(
                session.scalars(
                    select(AgentRunRecord)
                    .where(*filters)
                    .order_by(
                        AgentRunRecord.created_at.desc(), AgentRunRecord.id.desc()
                    )
                    .limit(bounded_limit + 1)
                ).all()
            )

        has_more = len(rows) > bounded_limit
        page_rows = rows[:bounded_limit]
        next_cursor = (
            _encode_run_cursor(page_rows[-1]) if has_more and page_rows else None
        )
        summaries: list[dict[str, Any]] = []
        for row in page_rows:
            summary = self._to_run_summary(row)
            raw_task_state = self.get_task_state(
                row.id,
                run_version=int(row.active_run_version),
            )
            if isinstance(raw_task_state, dict):
                try:
                    typed_task_state = AgentTaskState.model_validate(raw_task_state)
                except (TypeError, ValueError):
                    typed_task_state = None
                if typed_task_state is not None:
                    summary["current_iteration"] = typed_task_state.current_iteration
                    summary["task_state"] = typed_task_state.model_dump(
                        mode="json"
                    )
            summaries.append(summary)
        pagination = {
            "cursor": cursor,
            "next_cursor": next_cursor,
            "has_more": has_more,
            "total": total,
            "limit": bounded_limit,
        }
        return {
            "runs": summaries,
            "pagination": pagination,
            "next_cursor": next_cursor,
            "has_more": has_more,
            "total": total,
        }

    # -------------------------------------------------------------------------
    def list_run_summaries(
        self,
        conversation_id: str,
        *,
        query: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
        include_terminal: bool = True,
    ) -> dict[str, Any]:
        """Return recent-run summaries using the API-facing spelling."""

        return self.list_runs_for_conversation(
            conversation_id,
            query=query,
            cursor=cursor,
            limit=limit,
            include_terminal=include_terminal,
        )

    # -------------------------------------------------------------------------
    def read_trace(
        self,
        conversation_id: str,
        run_id: str,
        *,
        run_version: int | None = None,
        after_sequence: int | None = None,
        cursor: str | None = None,
        limit: int = 100,
        include_internal: bool = True,
    ) -> dict[str, Any]:
        """Read a redacted operational trace for one conversation run.

        Trace rows are read directly from ``agent_run_events`` so internal
        checkpoints and trace events can be included for an authenticated
        inspector.  Payloads are bounded and redacted at this boundary; this
        method never returns provider credentials, raw payload bodies, or
        chain-of-thought/reasoning fields.
        """

        normalized_conversation_id = str(conversation_id).strip()
        normalized_run_id = str(run_id).strip()
        if not normalized_conversation_id or not normalized_run_id:
            raise ValueError("Conversation and run ids are required.")
        bounded_limit = max(1, min(int(limit), self.MAX_TRACE_LIMIT))
        parsed_cursor = _parse_sequence_cursor(cursor)
        effective_after = max(
            value
            for value in (after_sequence or 0, parsed_cursor or 0)
        )
        if effective_after < 0:
            raise ValueError("after_sequence must be non-negative.")
        if run_version is not None and run_version < 1:
            raise ValueError("run_version must be positive.")

        with self._session_factory() as session:
            run = session.scalar(
                select(AgentRunRecord).where(
                    AgentRunRecord.id == normalized_run_id,
                    AgentRunRecord.conversation_id == normalized_conversation_id,
                )
            )
            if run is None:
                raise ValueError("Run not found.")
            filters: list[Any] = [
                AgentRunEventRecord.run_id == normalized_run_id,
                AgentRunEventRecord.conversation_id == normalized_conversation_id,
            ]
            if run_version is not None:
                filters.append(AgentRunEventRecord.run_version == run_version)
            if not include_internal:
                filters.append(AgentRunEventRecord.visibility == "user")
            total = int(
                session.scalar(
                    select(func.count())
                    .select_from(AgentRunEventRecord)
                    .where(*filters)
                )
                or 0
            )
            page_filters = list(filters)
            if effective_after:
                page_filters.append(AgentRunEventRecord.sequence > effective_after)
            rows = list(
                session.scalars(
                    select(AgentRunEventRecord)
                    .where(*page_filters)
                    .order_by(AgentRunEventRecord.sequence.asc())
                    .limit(bounded_limit + 1)
                ).all()
            )

        has_more = len(rows) > bounded_limit
        page_rows = rows[:bounded_limit]
        next_cursor = str(page_rows[-1].sequence) if has_more and page_rows else None
        events = [self._to_trace_event(row) for row in page_rows]
        pagination = {
            "cursor": cursor,
            "next_cursor": next_cursor,
            "has_more": has_more,
            "total": total,
            "limit": bounded_limit,
            "after_sequence": effective_after or None,
        }
        return {
            "conversation_id": normalized_conversation_id,
            "run_id": normalized_run_id,
            "run_version": run_version,
            "events": events,
            "pagination": pagination,
            "next_cursor": next_cursor,
            "has_more": has_more,
            "total": total,
        }

    # -------------------------------------------------------------------------
    def get_run_trace(
        self,
        conversation_id: str,
        run_id: str,
        *,
        run_version: int | None = None,
        after_sequence: int | None = None,
        cursor: str | None = None,
        limit: int = 100,
        include_internal: bool = True,
    ) -> dict[str, Any]:
        """Alias for :meth:`read_trace` used by API adapters."""

        return self.read_trace(
            conversation_id,
            run_id,
            run_version=run_version,
            after_sequence=after_sequence,
            cursor=cursor,
            limit=limit,
            include_internal=include_internal,
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _to_run_summary(record: AgentRunRecord) -> dict[str, Any]:
        started = _aware_datetime(record.started_at)
        completed = _aware_datetime(record.completed_at)
        duration_ms = (
            max(0, int((completed - started).total_seconds() * 1000))
            if started is not None and completed is not None
            else None
        )
        return {
            "run_id": record.id,
            "conversation_id": record.conversation_id,
            "run_version": int(record.active_run_version),
            "active_run_version": int(record.active_run_version),
            "state": record.state,
            "original_request": record.original_request[:2_000],
            "aggregated_request": record.aggregated_request[:2_000],
            "request_timezone": record.request_timezone,
            "created_at": _iso_datetime(record.created_at),
            "started_at": _iso_datetime(record.started_at),
            "completed_at": _iso_datetime(record.completed_at),
            "cancel_requested_at": _iso_datetime(record.cancel_requested_at),
            "error_code": record.error_code,
            "error_message": _safe_trace_string(record.error_message),
            "presentation_status": record.presentation_status,
            "duration_ms": duration_ms,
            "current_iteration": None,
            "task_state": None,
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def _to_trace_event(record: AgentRunEventRecord) -> dict[str, Any]:
        payload = redact_trace_payload(record.payload_json)
        event: dict[str, Any] = {
            "event_id": record.id,
            "run_id": record.run_id,
            "conversation_id": record.conversation_id,
            "sequence": int(record.sequence),
            "run_version": int(record.run_version),
            "type": record.type,
            "visibility": record.visibility,
            "timestamp": _iso_datetime(record.created_at),
            "payload": payload,
        }
        # Native trace events are persisted as an envelope whose operational
        # fields live in ``payload`` (and, for AgentTraceEvent, often one
        # level deeper in ``payload.payload``).  Flatten only the small UI/API
        # projection fields; retain the redacted envelope for full inspection.
        event["kind"] = str(payload.get("kind") or record.type)
        nested = payload.get("payload")
        nested_payload = (
            cast(dict[str, Any], nested) if isinstance(nested, dict) else {}
        )
        for key, aliases in {
            "task_id": ("task_id", "active_task_id"),
            "tool_name": ("tool_name", "tool"),
            "call_id": ("call_id", "tool_call_id"),
            "iteration": ("iteration", "current_iteration"),
            "label": ("label",),
            "status": ("status",),
            "summary": ("summary", "message"),
            "duration_ms": ("duration_ms", "duration"),
            "evidence_refs": ("evidence_refs", "evidence_ids"),
            "retryable": ("retryable",),
            "error": ("error", "error_message", "failure"),
        }.items():
            for alias in aliases:
                candidate = payload.get(alias)
                if candidate is None:
                    candidate = nested_payload.get(alias)
                if candidate is not None:
                    event[key] = candidate
                    break
        return event

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
            if record.presentation_status == "pending":
                record.presentation_status = "failed"
            finalized_presentation = _finalize_pending_presentation(
                record.presentation_json,
                status="failed",
            )
            if finalized_presentation is not None:
                record.presentation_json = finalized_presentation
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
                        # A cancelled browser candidate is no longer pending;
                        # preserve non-render terminal values for ordinary
                        # text runs while closing the render lifecycle.
                        presentation_status=case(
                            (
                                AgentRunRecord.presentation_status == "pending",
                                "failed",
                            ),
                            else_=AgentRunRecord.presentation_status,
                        ),
                    )
                ),
            )
            record = self._require_run(session, run_id)
            if int(updated.rowcount or 0) == 1:
                finalized_presentation = _finalize_pending_presentation(
                    record.presentation_json,
                    status="failed",
                )
                if finalized_presentation is not None:
                    record.presentation_json = finalized_presentation
            session.commit()
            return self._to_snapshot(record), int(updated.rowcount or 0) == 1

    # -------------------------------------------------------------------------
    def mark_completed_if_current(
        self,
        run_id: str,
        expected_run_version: int,
        *,
        presentation_status: str | None = None,
    ) -> tuple[AgentRunSnapshot, bool]:
        """Complete only the still-current, non-cancelled run version."""
        with self._session_factory() as session:
            values: dict[str, Any] = {
                "state": AgentRunState.COMPLETED.value,
                "active_slot": None,
                "completed_at": datetime.now(UTC),
            }
            if presentation_status is not None:
                values["presentation_status"] = presentation_status
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
                    .values(**values)
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
        prepared_at = datetime.now(UTC)
        with self._session_factory() as session:
            record = self._require_run(session, run_id)
            previous_presentation = _json_object(record.presentation_json)
            merged_presentation = dict(presentation)
            previous_attempts = int(
                previous_presentation.get("render_attempts") or 0
            )
            merged_presentation["render_attempts"] = max(
                previous_attempts,
                int(presentation.get("render_attempts") or 0),
            )
            previous_observations: list[JsonObject] = [
                item
                for item in _json_list(previous_presentation.get("render_observations"))
                if isinstance(item, dict)
            ]
            current_observations: list[JsonObject] = [
                item
                for item in _json_list(presentation.get("render_observations"))
                if isinstance(item, dict)
            ]
            merged_presentation["render_observations"] = [
                *previous_observations,
                *current_observations,
            ][-8:]
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
                        presentation_json=merged_presentation,
                        render_prepared_at=prepared_at,
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
        resume: bool = False,
        observation: dict[str, Any] | None = None,
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
            if resume and presentation.get("acknowledgment") == acknowledgment:
                return self._to_snapshot(run), True, presentation
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
                            "render_verified",
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
            if resume:
                # A browser result is an observation in the native run, not a
                # terminal response.  Persist the observation and updated
                # checkpoint before releasing the transaction so the lifecycle
                # service can safely requeue this exact run.
                checkpoint = _json_object(
                    _json_object(pending_response.get("execution_trace")).get(
                        "checkpoint"
                    )
                )
                if not checkpoint:
                    raise ValueError("Prepared map checkpoint is missing.")
                render_attempt = max(
                    int(presentation.get("render_attempts") or 0),
                    int(checkpoint.get("render_attempts") or 0),
                ) + 1
                render_observation = dict(observation or {})
                render_observation.setdefault("attempt", render_attempt)
                observations: list[JsonObject] = [
                    item
                    for item in _json_list(checkpoint.get("render_observations"))
                    if isinstance(item, dict)
                ]
                observations.append(render_observation)
                checkpoint["render_observations"] = observations[-8:]
                checkpoint["render_attempts"] = render_attempt
                checkpoint["render_verified"] = status == "ready"
                checkpoint["render_retry_exhausted"] = bool(
                    render_observation.get("recovery") == "terminal"
                )
                prepared_action_fingerprint = str(
                    checkpoint.get("prepared_map_action_fingerprint") or ""
                )
                checkpoint["prepared_map_session"] = None
                checkpoint["prepared_map_action_fingerprint"] = None
                checkpoint["phase"] = "update_state"
                checkpoint["termination_reason"] = None
                budget_snapshot = _json_object(checkpoint.get("budget_snapshot"))
                for key in ("terminal_reason", "stopping_reason", "terminal_stage"):
                    budget_snapshot[key] = None
                checkpoint["budget_snapshot"] = budget_snapshot
                if status == "failed":
                    fingerprint = prepared_action_fingerprint or str(
                        render_observation.get("fingerprint") or ""
                    )
                    if fingerprint:
                        failed_fingerprints = _json_object(
                            checkpoint.get("failed_render_fingerprints")
                        )
                        failed_fingerprints[fingerprint] = int(
                            failed_fingerprints.get(fingerprint) or 0
                        ) + 1
                        checkpoint["failed_render_fingerprints"] = dict(
                            list(failed_fingerprints.items())[-32:]
                        )
                else:
                    candidate_map = pending_response.get("map_session")
                    conversation = session.get(ConversationRecord, conversation_id)
                    if conversation is None:
                        raise ValueError("Conversation not found.")
                    state = ConversationState.from_persisted(
                        conversation_id,
                        pending_response.get("conversation_state")
                        or conversation.conversation_state,
                        revision=int(conversation.context_revision),
                    )
                    conversation.context_revision += 1
                    if isinstance(candidate_map, dict):
                        try:
                            committed_map = MapSession.model_validate(candidate_map)
                        except (TypeError, ValueError) as exc:
                            raise ValueError(
                                "Prepared map does not match the current contract."
                            ) from exc
                        state = state.model_copy(
                            update={
                                "revision": conversation.context_revision,
                                "committed_map_session": committed_map,
                            }
                        )
                        checkpoint["active_map_session"] = candidate_map
                    else:
                        state = state.model_copy(
                            update={"revision": conversation.context_revision}
                        )
                    conversation.conversation_state = state.model_dump(mode="json")
                    pending_response["conversation_state"] = state.model_dump(
                        mode="json"
                    )
                    pending_response["context_revision"] = conversation.context_revision
                    checkpoint["conversation_revision"] = conversation.context_revision
                execution_trace = _json_object(pending_response.get("execution_trace"))
                execution_trace["checkpoint"] = checkpoint
                execution_trace["termination_reason"] = None
                execution_trace["render_observation"] = render_observation
                pending_response["execution_trace"] = execution_trace
                pending_response["presentation_status"] = (
                    "ready" if status == "ready" else "pending"
                )
                run.state = AgentRunState.PENDING.value
                run.active_slot = 1
                run.completed_at = None
                run.error_code = None
                run.error_message = None
                run.presentation_status = "ready" if status == "ready" else "pending"
                updated_presentation = {
                    **presentation,
                    "status": "resuming",
                    "acknowledgment": acknowledgment,
                    "render_observation": render_observation,
                    "render_attempts": render_attempt,
                    # Keep the presentation envelope inspectable between the
                    # acknowledgement transaction and the resumed worker.
                    # The checkpoint is the canonical state consumed by the
                    # agent, but this bounded projection is also returned by
                    # run-status and must not lag behind the observation that
                    # was just accepted.
                    "render_observations": observations[-8:],
                    "render_retry_exhausted": bool(
                        render_observation.get("recovery") == "terminal"
                    ),
                    "pending_response": pending_response,
                }
                run.presentation_json = updated_presentation
                run.render_prepared_at = None
                session.commit()
                session.refresh(run)
                return self._to_snapshot(run), False, pending_response
            if status == "ready":
                conversation = session.get(ConversationRecord, conversation_id)
                if conversation is None:
                    raise ValueError("Conversation not found.")
                candidate_map = pending_response.get("map_session")
                state = ConversationState.from_persisted(
                    conversation_id,
                    pending_response.get("conversation_state")
                    or conversation.conversation_state,
                    revision=int(conversation.context_revision),
                )
                conversation.context_revision += 1
                if isinstance(candidate_map, dict):
                    try:
                        committed_map = MapSession.model_validate(candidate_map)
                    except (TypeError, ValueError) as exc:
                        raise ValueError("Prepared map does not match the current contract.") from exc
                    state = state.model_copy(
                        update={
                            "revision": conversation.context_revision,
                            "committed_map_session": committed_map,
                        }
                    )
                else:
                    state = state.model_copy(
                        update={"revision": conversation.context_revision}
                    )
                conversation.conversation_state = state.model_dump(mode="json")
                pending_response["context_revision"] = conversation.context_revision
                final_assistant_message = _final_render_message(pending_response)
                pending_response["assistant_message"] = final_assistant_message
                assistant_message = session.scalar(
                    select(ChatMessageRecord).where(
                        ChatMessageRecord.conversation_id == conversation_id,
                        ChatMessageRecord.role == "assistant",
                        ChatMessageRecord.request_id == run_id,
                    )
                )
                if assistant_message is not None:
                    assistant_message.content = final_assistant_message
                    assistant_message.map_session = candidate_map
                    stored_payload = _json_object(assistant_message.structured_payload)
                    if stored_payload:
                        assistant_message.structured_payload = {
                            **stored_payload,
                            "map_session": candidate_map,
                            "presentation_status": "ready",
                        }
                task_state = _terminal_task_state_payload(
                    pending_response.get("task_state"), status="completed"
                )
                if task_state is not None:
                    pending_response["task_state"] = task_state
                run.state = AgentRunState.COMPLETED.value
                run.completed_at = datetime.now(UTC)
                run.presentation_status = "ready"
                updated_presentation: JsonObject = {
                    **presentation,
                    "status": "ready",
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
                updated_presentation.pop("pending_response", None)
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
                task_state = _terminal_task_state_payload(
                    pending_response.get("task_state"), status="failed"
                )
                if task_state is not None:
                    pending_response["task_state"] = task_state
                run.state = AgentRunState.FAILED.value
                run.completed_at = datetime.now(UTC)
                run.error_code = str(acknowledgment.get("failure_code") or "render_failed")
                run.error_message = "The prepared map could not be rendered."
                run.presentation_status = "failed"
                updated_presentation = {
                    **presentation,
                    "status": "failed",
                    "acknowledgment": acknowledgment,
                    "error_code": run.error_code,
                }
                updated_presentation.pop("pending_response", None)
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
            run.render_prepared_at = None
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
    def expire_pending_render(
        self,
        *,
        conversation_id: str,
        run_id: str,
        run_version: int,
        timeout_seconds: float = 90.0,
    ) -> AgentRunSnapshot | None:
        """Fail a stale candidate while preserving the last committed map."""

        cutoff = datetime.now(UTC) - timedelta(seconds=max(0.1, timeout_seconds))
        with self._session_factory() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            run = session.scalar(
                select(AgentRunRecord).where(
                    AgentRunRecord.id == run_id,
                    AgentRunRecord.conversation_id == conversation_id,
                    AgentRunRecord.active_run_version == run_version,
                    AgentRunRecord.state == AgentRunState.AWAITING_RENDER.value,
                    AgentRunRecord.presentation_status == "pending",
                )
            )
            if run is None:
                return None
            prepared_at = run.render_prepared_at or run.started_at or run.created_at
            prepared_at = (
                prepared_at.replace(tzinfo=UTC)
                if prepared_at.tzinfo is None
                else prepared_at
            )
            if prepared_at > cutoff:
                return None
            run.state = AgentRunState.FAILED.value
            run.active_slot = None
            run.completed_at = datetime.now(UTC)
            run.error_code = "render_timeout"
            run.error_message = "The browser did not acknowledge the prepared map before the render deadline."
            run.presentation_status = "render_timeout"
            presentation = _json_object(run.presentation_json)
            finalized_presentation = _finalize_pending_presentation(
                presentation,
                status="render_timeout",
                error_code="render_timeout",
                force=True,
            ) or {
                "status": "render_timeout",
                "error_code": "render_timeout",
            }
            durable_event_ids = [
                str(item)
                for item in _json_list(presentation.get("durable_event_ids"))
                if str(item).strip()
            ]
            if self._event_repository is not None:
                timeout_event = self._event_repository.append_event_in_session(
                    session,
                    RunEventCreate(
                        conversation_id=conversation_id,
                        run_id=run_id,
                        run_version=run_version,
                        type=RunEventType.ERROR,
                        visibility=RunEventVisibility.USER,
                        payload={
                            "code": "render_timeout",
                            "message": run.error_message,
                            "presentation_status": "render_timeout",
                            "state": AgentRunState.FAILED.value,
                        },
                    ),
                )
                durable_event_ids.append(timeout_event.event_id)
            if durable_event_ids:
                finalized_presentation["durable_event_ids"] = durable_event_ids
            run.presentation_json = finalized_presentation
            session.commit()
            session.refresh(run)
            return self._to_snapshot(run)

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
        self,
        run_id: str,
        expected_run_version: int,
        code: str,
        message: str,
        *,
        presentation_status: str | None = None,
    ) -> tuple[AgentRunSnapshot, bool]:
        """Fail only the still-current, non-cancelled run version."""
        with self._session_factory() as session:
            # ``pending`` is a presentation-in-progress value, never a valid
            # terminal outcome. Normalize an explicit stale value here as
            # well as the default pending-to-failed case below so every
            # failure commit closes the presentation lifecycle atomically.
            if presentation_status == "pending":
                presentation_status = "failed"
            if presentation_status is not None and presentation_status not in {
                "not_required",
                "pending",
                "ready",
                "failed",
                "render_timeout",
            }:
                raise ValueError("Unsupported terminal presentation status.")
            status_value: object = (
                presentation_status
                if presentation_status is not None
                else case(
                    (AgentRunRecord.presentation_status == "pending", "failed"),
                    else_=AgentRunRecord.presentation_status,
                )
            )
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
                        presentation_status=status_value,
                    )
                ),
            )
            record = self._require_run(session, run_id)
            terminal_status = presentation_status or "failed"
            if int(updated.rowcount or 0) == 1:
                finalized_presentation = _finalize_pending_presentation(
                    record.presentation_json,
                    status=terminal_status,
                    error_code=code,
                )
                if finalized_presentation is not None:
                    record.presentation_json = finalized_presentation
            session.commit()
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
            if record.presentation_status == "pending":
                record.presentation_status = "failed"
            finalized_presentation = _finalize_pending_presentation(
                record.presentation_json,
                status=record.presentation_status,
                error_code=code,
            )
            if finalized_presentation is not None:
                record.presentation_json = finalized_presentation
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
                Literal["not_required", "pending", "ready", "failed", "render_timeout"],
                record.presentation_status
                if record.presentation_status
                in {"not_required", "pending", "ready", "failed", "render_timeout"}
                else "not_required",
            ),
            presentation=record.presentation_json,
        )


###############################################################################
def _task_state_from_payload(payload: JsonObject) -> dict[str, Any] | None:
    """Locate a bounded task ledger in a known native event envelope."""

    candidates: list[object] = [payload.get("task_state")]
    nested = payload.get("payload")
    if isinstance(nested, dict):
        nested_object = cast(JsonObject, nested)
        candidates.append(nested_object.get("task_state"))
        checkpoint_state = nested_object.get("run_state")
        if isinstance(checkpoint_state, dict):
            candidates.append(cast(JsonObject, checkpoint_state).get("task_state"))
    for candidate in candidates:
        if isinstance(candidate, dict):
            return dict(cast(dict[str, Any], candidate))
    return None


def _terminal_task_state_payload(
    value: object,
    *,
    status: Literal["completed", "failed"],
) -> dict[str, Any] | None:
    """Promote the persisted task ledger with the render terminal state.

    Render acknowledgment is the final server-owned observation for map
    runs.  It must update the same run-scoped ledger that was emitted while
    awaiting the browser; otherwise the run row becomes terminal while its
    public task projection remains ``in_progress``.
    """

    if not isinstance(value, dict):
        return None
    try:
        typed = AgentTaskState.model_validate(value)
    except (TypeError, ValueError):
        return None
    requirements = [
        item.model_copy(update={"status": "satisfied" if status == "completed" else "failed"})
        for item in typed.completion_requirements
    ]
    tasks = [item.model_copy(update={"status": status}) for item in typed.tasks]
    return typed.model_copy(
        update={
            "active_task_id": typed.root_task_id,
            "status": status,
            "tasks": tasks,
            "completion_requirements": requirements,
        }
    ).model_dump(mode="json", exclude_none=True)


###############################################################################
def _final_render_message(pending_response: JsonObject) -> str:
    """Replace the transient render-wait text with a durable terminal result."""

    current = str(pending_response.get("assistant_message") or "").strip()
    if current not in {
        "",
        "Data prepared; the map is loading.",
        "A map candidate is prepared and awaiting render acknowledgment.",
        "The map candidate is awaiting render acknowledgment.",
    }:
        return current

    map_session = _json_object(pending_response.get("map_session"))
    collection = _json_object(map_session.get("overlay_collection"))
    instances = [
        cast(JsonObject, item)
        for item in _json_list(collection.get("instances"))
        if isinstance(item, dict)
    ]
    statuses = [
        str(_json_object(instance.get("descriptor")).get("result_status") or "")
        .strip()
        .casefold()
        for instance in instances
    ]
    top_level_status = (
        str(_json_object(map_session.get("payload")).get("result_status") or "")
        .strip()
        .casefold()
    )
    if top_level_status == "valid_empty" or (
        statuses and all(status == "valid_empty" for status in statuses)
    ):
        return "The map is ready. No results were found in the requested area or time window."

    feature_count = 0
    for instance in instances:
        data = _json_object(_json_object(instance.get("descriptor")).get("data"))
        features = _json_list(data.get("features"))
        feature_count += len(features)
    if feature_count:
        noun = "result" if feature_count == 1 else "results"
        return f"The map is ready with {feature_count} {noun}."
    return "The map is ready."


###############################################################################
_TRACE_SECRET_MARKERS = (
    "authorization",
    "access_token",
    "api_key",
    "apikey",
    "password",
    "secret",
    "cookie",
    "credential",
    "private_key",
    "client_secret",
)
_TRACE_REASONING_KEYS = {
    "analysis",
    "chain_of_thought",
    "chainofthought",
    "deliberation",
    "hidden_reasoning",
    "internal_reasoning",
    "scratchpad",
    "thought",
    "thoughts",
    "reasoning",
}
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_SECRET_VALUE_PATTERN = re.compile(
    r"(?i)\b(?:sk|pk|ghp|gsk|xox[baprs])-[A-Za-z0-9_-]{8,}\b"
)
_NAMED_SECRET_PATTERN = re.compile(
    r"(?i)\b(?:api[_ -]?key|access[_ -]?token|password|secret|credential)"
    r"\s*[:=]\s*[^\s,;]+"
)


###############################################################################
def redact_trace_payload(
    value: object,
    *,
    max_depth: int = 8,
    max_items: int = 128,
    max_string_chars: int = 4_096,
) -> JsonObject:
    """Return a bounded operational payload safe for a run inspector.

    This is deliberately independent of provider-specific payload models.
    Trace records have historically accepted JSON objects from several
    execution layers, so the repository boundary applies a conservative
    recursive policy: remove credential/reasoning fields, cap collection and
    string sizes, and retain scalar operational metadata.
    """

    safe = _redact_trace_value(
        value,
        depth=0,
        max_depth=max_depth,
        max_items=max_items,
        max_string_chars=max_string_chars,
    )
    if isinstance(safe, dict):
        return cast(JsonObject, safe)
    if isinstance(safe, list):
        return {"items": safe}
    return {"value": safe}


###############################################################################
def _redact_trace_value(
    value: object,
    *,
    depth: int,
    max_depth: int,
    max_items: int,
    max_string_chars: int,
) -> Any:
    if depth >= max_depth:
        return "[depth-limited]"
    if isinstance(value, dict):
        mapping = cast(dict[Any, Any], value)
        result: dict[str, Any] = {}
        for index, (raw_key, raw_value) in enumerate(mapping.items()):
            if index >= max_items:
                result["_truncated_keys"] = True
                break
            key = str(raw_key)
            normalized_key = key.casefold().replace("-", "_").replace(" ", "_")
            if _is_trace_secret_key(normalized_key):
                continue
            if normalized_key in _TRACE_REASONING_KEYS:
                continue
            result[key] = _redact_trace_value(
                raw_value,
                depth=depth + 1,
                max_depth=max_depth,
                max_items=max_items,
                max_string_chars=max_string_chars,
            )
        return result
    if isinstance(value, list):
        items = cast(list[Any], value)
        bounded = [
            _redact_trace_value(
                item,
                depth=depth + 1,
                max_depth=max_depth,
                max_items=max_items,
                max_string_chars=max_string_chars,
            )
            for item in items[:max_items]
        ]
        if len(items) > max_items:
            bounded.append("[items-truncated]")
        return bounded
    if isinstance(value, tuple):
        items = cast(tuple[Any, ...], value)
        return _redact_trace_value(
            list(items),
            depth=depth,
            max_depth=max_depth,
            max_items=max_items,
            max_string_chars=max_string_chars,
        )
    if isinstance(value, bytes):
        return "[binary-redacted]"
    if isinstance(value, str):
        safe_value = _BEARER_PATTERN.sub("[redacted bearer token]", value)
        safe_value = _SECRET_VALUE_PATTERN.sub("[redacted secret]", safe_value)
        safe_value = _NAMED_SECRET_PATTERN.sub("[redacted secret]", safe_value)
        if len(safe_value) > max_string_chars:
            return f"{safe_value[: max_string_chars - 1]}…"
        return safe_value
    return value


###############################################################################
def _is_trace_secret_key(normalized_key: str) -> bool:
    return any(marker in normalized_key for marker in _TRACE_SECRET_MARKERS)


###############################################################################
def _safe_trace_string(value: str | None) -> str | None:
    if value is None:
        return None
    return str(
        _redact_trace_value(
            value,
            depth=0,
            max_depth=1,
            max_items=1,
            max_string_chars=2_000,
        )
    )


###############################################################################
def _iso_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


###############################################################################
def _aware_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


###############################################################################
def _sqlite_contains_pattern(value: str) -> str:
    escaped = value.casefold().replace("\\", "\\\\")
    escaped = escaped.replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


###############################################################################
def _encode_run_cursor(row: AgentRunRecord) -> str:
    timestamp = row.created_at.isoformat() if row.created_at else ""
    payload = json.dumps(
        {"created_at": timestamp, "run_id": row.id},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


###############################################################################
def _decode_run_cursor(cursor: str | None) -> tuple[datetime, str] | None:
    if cursor is None or not str(cursor).strip():
        return None
    encoded = str(cursor).strip()
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(decoded.decode("utf-8"))
        timestamp = datetime.fromisoformat(str(payload.get("created_at") or ""))
        run_id = str(payload.get("run_id") or "").strip()
    except (ValueError, TypeError, KeyError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid run cursor.") from exc
    if not run_id:
        raise ValueError("Invalid run cursor.")
    if timestamp.tzinfo is not None:
        timestamp = timestamp.astimezone(UTC).replace(tzinfo=None)
    return timestamp, run_id


###############################################################################
def _parse_sequence_cursor(cursor: str | None) -> int | None:
    if cursor is None or not str(cursor).strip():
        return None
    value = str(cursor).strip()
    if not value.isdigit():
        raise ValueError("Invalid trace cursor.")
    return max(0, int(value))
