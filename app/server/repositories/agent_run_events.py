from __future__ import annotations

from server.common.typing import json_object

from uuid import uuid4

from sqlalchemy import func, select, update

from server.contracts.events import (
    RunEvent,
    RunEventCreate,
    RunEventType,
    RunEventVisibility,
)
from server.repositories.database.contracts import DatabaseBackend
from server.repositories.schemas.models import AgentRunEventRecord, AgentRunRecord

###############################################################################
class AgentRunEventRepository:

    # -------------------------------------------------------------------------
    def __init__(self, database: DatabaseBackend) -> None:
        self._session_factory = database.session

    # -------------------------------------------------------------------------
    def append_event(self, event: RunEventCreate) -> RunEvent:
        with self._session_factory() as session:
            sequence = session.scalar(
                update(AgentRunRecord)
                .where(
                    AgentRunRecord.id == event.run_id,
                    AgentRunRecord.conversation_id == event.conversation_id,
                )
                .values(next_event_sequence=AgentRunRecord.next_event_sequence + 1)
                .returning(AgentRunRecord.next_event_sequence)
            )
            if sequence is None:
                raise ValueError("Run not found.")
            record = AgentRunEventRecord(
                id=f"evt_{uuid4().hex}",
                run_id=event.run_id,
                conversation_id=event.conversation_id,
                sequence=sequence,
                run_version=event.run_version,
                type=event.type.value,
                visibility=event.visibility.value,
                payload_json=event.payload,
                created_at=event.timestamp,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._to_domain(record)

    # -------------------------------------------------------------------------
    def list_events(
        self,
        run_id: str,
        *,
        after_sequence: int | None = None,
        visibility: str = "user",
    ) -> list[RunEvent]:
        threshold = after_sequence
        with self._session_factory() as session:
            statement = select(AgentRunEventRecord).where(
                AgentRunEventRecord.run_id == run_id
            )
            if visibility == "user":
                statement = statement.where(AgentRunEventRecord.visibility == "user")
            if threshold is not None:
                statement = statement.where(AgentRunEventRecord.sequence > threshold)
            rows = (
                session.execute(statement.order_by(AgentRunEventRecord.sequence.asc()))
                .scalars()
                .all()
            )
        return [self._to_domain(row) for row in rows]

    # -------------------------------------------------------------------------
    def get_last_sequence(self, run_id: str) -> int:
        with self._session_factory() as session:
            return int(
                session.scalar(
                    select(
                        func.coalesce(func.max(AgentRunEventRecord.sequence), 0)
                    ).where(AgentRunEventRecord.run_id == run_id)
                )
                or 0
            )

    # -------------------------------------------------------------------------
    @staticmethod
    def _to_domain(record: AgentRunEventRecord) -> RunEvent:
        payload = record.payload_json
        return RunEvent(
            event_id=record.id,
            sequence=record.sequence,
            conversation_id=record.conversation_id,
            run_id=record.run_id,
            run_version=record.run_version,
            type=RunEventType(record.type),
            timestamp=record.created_at,
            visibility=RunEventVisibility(record.visibility),
            payload=json_object(payload),
        )
