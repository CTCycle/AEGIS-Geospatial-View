from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select

from server.domain.steering import SteeringMessageRecord
from server.repositories.database.backend import get_database
from server.repositories.schemas.models import AgentSteeringMessageRecord, Base

###############################################################################
class AgentSteeringRepository:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        backend = get_database().backend
        Base.metadata.create_all(backend.engine)
        self._session_factory = backend.session

    # -------------------------------------------------------------------------
    def append_steering_message(
        self,
        run_id: str,
        content: str,
        client_mutation_id: str | None,
        run_version: int,
    ) -> SteeringMessageRecord:
        if client_mutation_id:
            existing = self.find_by_client_mutation_id(run_id, client_mutation_id)
            if existing is not None:
                return existing
        with self._session_factory() as session:
            record = AgentSteeringMessageRecord(
                id=f"steer_{uuid4().hex}",
                run_id=run_id,
                run_version=run_version,
                content=content,
                client_mutation_id=client_mutation_id,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._to_domain(record)

    # -------------------------------------------------------------------------
    def list_steering_messages(self, run_id: str) -> list[SteeringMessageRecord]:
        with self._session_factory() as session:
            rows = session.execute(
                select(AgentSteeringMessageRecord)
                .where(AgentSteeringMessageRecord.run_id == run_id)
                .order_by(AgentSteeringMessageRecord.created_at.asc())
            ).scalars().all()
            return [self._to_domain(row) for row in rows]

    # -------------------------------------------------------------------------
    def find_by_client_mutation_id(
        self,
        run_id: str,
        client_mutation_id: str,
    ) -> SteeringMessageRecord | None:
        with self._session_factory() as session:
            row = session.execute(
                select(AgentSteeringMessageRecord).where(
                    AgentSteeringMessageRecord.run_id == run_id,
                    AgentSteeringMessageRecord.client_mutation_id == client_mutation_id,
                )
            ).scalars().first()
            return self._to_domain(row) if row is not None else None

    # -------------------------------------------------------------------------
    @staticmethod
    def _to_domain(record: AgentSteeringMessageRecord) -> SteeringMessageRecord:
        return SteeringMessageRecord(
            steering_id=record.id,
            run_id=record.run_id,
            run_version=record.run_version,
            content=record.content,
            client_mutation_id=record.client_mutation_id,
            created_at=record.created_at,
        )
