from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from server.domain.agent_runs import AgentRunSnapshot, AgentRunState
from server.repositories.database.backend import get_database
from server.repositories.schemas.models import AgentRunRecord, Base, ConversationRecord

###############################################################################
class AgentRunRepository:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        backend = get_database().backend
        Base.metadata.create_all(backend.engine)
        self._session_factory = backend.session

    # -------------------------------------------------------------------------
    def create_run(
        self,
        conversation_id: str,
        original_request: str,
        aggregated_request: str,
    ) -> AgentRunSnapshot:
        with self._session_factory() as session:
            conversation = session.get(ConversationRecord, conversation_id)
            if conversation is None:
                raise ValueError("Conversation not found.")
            record = AgentRunRecord(
                id=f"run_{uuid4().hex}",
                conversation_id=conversation_id,
                original_request=original_request,
                aggregated_request=aggregated_request,
                active_run_version=1,
                state=AgentRunState.PENDING.value,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._to_snapshot(record)

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
            conversation = session.get(ConversationRecord, conversation_id)
            if conversation is None or not conversation.active_run_id:
                return None
            record = session.get(AgentRunRecord, conversation.active_run_id)
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
            record.cancel_requested_at = record.cancel_requested_at or datetime.now(UTC)
            record.completed_at = record.completed_at or datetime.now(UTC)
            session.commit()
            session.refresh(record)
            return self._to_snapshot(record)

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
    def mark_completed(self, run_id: str) -> AgentRunSnapshot:
        with self._session_factory() as session:
            record = self._require_run(session, run_id)
            record.state = AgentRunState.COMPLETED.value
            record.completed_at = datetime.now(UTC)
            session.commit()
            session.refresh(record)
            return self._to_snapshot(record)

    # -------------------------------------------------------------------------
    def mark_failed(self, run_id: str, code: str, message: str) -> AgentRunSnapshot:
        with self._session_factory() as session:
            record = self._require_run(session, run_id)
            record.state = AgentRunState.FAILED.value
            record.error_code = code
            record.error_message = message
            record.completed_at = datetime.now(UTC)
            session.commit()
            session.refresh(record)
            return self._to_snapshot(record)

    # -------------------------------------------------------------------------
    @staticmethod
    def _require_run(session, run_id: str) -> AgentRunRecord:
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
