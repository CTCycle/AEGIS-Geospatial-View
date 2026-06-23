from __future__ import annotations

import json
from uuid import uuid4

from sqlalchemy import func, select

from server.domain.run_events import RunEvent, RunEventCreate, RunEventType, RunEventVisibility
from server.repositories.database.backend import get_database
from server.repositories.schemas.models import AgentRunEventRecord, Base

###############################################################################
class AgentRunEventRepository:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        backend = get_database().backend
        Base.metadata.create_all(backend.engine)
        self._session_factory = backend.session

    # -------------------------------------------------------------------------
    def append_event(self, event: RunEventCreate) -> RunEvent:
        with self._session_factory() as session:
            sequence = int(
                session.scalar(
                    select(func.coalesce(func.max(AgentRunEventRecord.sequence), 0)).where(
                        AgentRunEventRecord.run_id == event.run_id
                    )
                )
                or 0
            ) + 1
            record = AgentRunEventRecord(
                id=f"evt_{uuid4().hex}",
                run_id=event.run_id,
                conversation_id=event.conversation_id,
                sequence=sequence,
                run_version=event.run_version,
                type=event.type.value,
                visibility=event.visibility.value,
                payload_json=json.dumps(event.payload, default=str),
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
        after_event_id: str | None = None,
        after_sequence: int | None = None,
        visibility: str = "user",
    ) -> list[RunEvent]:
        threshold = after_sequence
        if threshold is None and after_event_id:
            found = self.find_event(run_id, after_event_id)
            threshold = found.sequence if found is not None else None
        with self._session_factory() as session:
            statement = select(AgentRunEventRecord).where(AgentRunEventRecord.run_id == run_id)
            if visibility == "user":
                statement = statement.where(AgentRunEventRecord.visibility == "user")
            if threshold is not None:
                statement = statement.where(AgentRunEventRecord.sequence > threshold)
            rows = session.execute(statement.order_by(AgentRunEventRecord.sequence.asc())).scalars().all()
            return [self._to_domain(row) for row in rows]

    # -------------------------------------------------------------------------
    def get_last_sequence(self, run_id: str) -> int:
        with self._session_factory() as session:
            return int(
                session.scalar(
                    select(func.coalesce(func.max(AgentRunEventRecord.sequence), 0)).where(
                        AgentRunEventRecord.run_id == run_id
                    )
                )
                or 0
            )

    # -------------------------------------------------------------------------
    def find_event(self, run_id: str, event_id: str) -> RunEvent | None:
        with self._session_factory() as session:
            row = session.execute(
                select(AgentRunEventRecord).where(
                    AgentRunEventRecord.run_id == run_id,
                    AgentRunEventRecord.id == event_id,
                )
            ).scalars().first()
            return self._to_domain(row) if row is not None else None

    # -------------------------------------------------------------------------
    @staticmethod
    def _to_domain(record: AgentRunEventRecord) -> RunEvent:
        try:
            payload = json.loads(record.payload_json)
        except json.JSONDecodeError:
            payload = {}
        return RunEvent(
            event_id=record.id,
            sequence=record.sequence,
            conversation_id=record.conversation_id,
            run_id=record.run_id,
            run_version=record.run_version,
            type=RunEventType(record.type),
            timestamp=record.created_at,
            visibility=RunEventVisibility(record.visibility),
            payload=payload if isinstance(payload, dict) else {},
        )
