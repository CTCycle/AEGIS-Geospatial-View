from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from server.contracts.runs import AgentRunSnapshot, AgentRunState
from server.repositories.database.sqlite import SQLiteRepository
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from server.repositories.schemas.models import AgentRunRecord, ConversationRecord

###############################################################################
class AgentRunRepository:

    # -------------------------------------------------------------------------
    def __init__(self, database: SQLiteRepository) -> None:
        self._session_factory = database.session

    # -------------------------------------------------------------------------
    def create_run(
        self,
        conversation_id: str,
        original_request: str,
        aggregated_request: str,
        client_request_id: str | None = None,
    ) -> AgentRunSnapshot:
        snapshot, _created = self.create_or_get_run(
            conversation_id,
            original_request,
            aggregated_request,
            client_request_id=client_request_id,
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
    ) -> tuple[AgentRunSnapshot, bool]:
        with self._session_factory() as session:
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
            record = AgentRunRecord(
                id=f"run_{uuid4().hex}",
                conversation_id=conversation_id,
                client_request_id=client_request_id,
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
                    AgentRunRecord.active_slot == 1,
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
                        AgentRunRecord.active_slot == 1,
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
            updated = cast(CursorResult[Any], session.execute(
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
            ))
            session.commit()
            record = self._require_run(session, run_id)
            return self._to_snapshot(record), int(updated.rowcount) == 1

    # -------------------------------------------------------------------------
    def mark_failed_if_current(
        self, run_id: str, expected_run_version: int, code: str, message: str
    ) -> tuple[AgentRunSnapshot, bool]:
        """Fail only the still-current, non-cancelled run version."""
        with self._session_factory() as session:
            updated = cast(CursorResult[Any], session.execute(
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
            ))
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
            started_at=record.started_at,
            completed_at=record.completed_at,
            cancel_requested_at=record.cancel_requested_at,
            error_code=record.error_code,
            error_message=record.error_message,
        )
