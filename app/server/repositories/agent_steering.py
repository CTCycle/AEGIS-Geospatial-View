from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from server.domain.steering import SteeringMessageRecord
from server.repositories.database.sqlite import SQLiteRepository
from server.repositories.schemas.models import AgentRunRecord, AgentSteeringMessageRecord

###############################################################################
class AgentSteeringRepository:

    # -------------------------------------------------------------------------
    def __init__(self, database: SQLiteRepository) -> None:
        self._session_factory = database.session

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
    def append_and_update_run(
        self,
        *,
        run_id: str,
        content: str,
        client_mutation_id: str | None,
        run_version: int,
        aggregated_request: str,
        expected_run_version: int | None = None,
    ) -> tuple[SteeringMessageRecord, int, str]:
        """Persist the steering mutation and its run version in one transaction."""
        with self._session_factory() as session:
            run = session.scalar(
                select(AgentRunRecord)
                .where(AgentRunRecord.id == run_id)
            )
            if run is None:
                raise ValueError("Run not found.")
            if client_mutation_id:
                existing = session.scalar(
                    select(AgentSteeringMessageRecord).where(
                        AgentSteeringMessageRecord.run_id == run_id,
                        AgentSteeringMessageRecord.client_mutation_id == client_mutation_id,
                    )
                )
                if existing is not None:
                    return self._to_domain(existing), run.active_run_version, run.aggregated_request
            if expected_run_version is not None and run.active_run_version != expected_run_version:
                raise ValueError("Run version conflict.")
            record = AgentSteeringMessageRecord(
                id=f"steer_{uuid4().hex}",
                run_id=run_id,
                run_version=run_version,
                content=content,
                client_mutation_id=client_mutation_id,
            )
            run.aggregated_request = aggregated_request
            run.active_run_version = run_version
            run.state = "updating"
            session.add(record)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise ValueError("Run version conflict.") from exc
            session.refresh(record)
            return self._to_domain(record), run_version, aggregated_request

    # -------------------------------------------------------------------------
    def mark_state_delta_applied(self, steering_id: str) -> SteeringMessageRecord:
        with self._session_factory() as session:
            record = session.get(AgentSteeringMessageRecord, steering_id)
            if record is None:
                raise ValueError("Steering message not found.")
            record.state_delta_applied = True
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
            state_delta_applied=record.state_delta_applied,
            created_at=record.created_at,
        )
