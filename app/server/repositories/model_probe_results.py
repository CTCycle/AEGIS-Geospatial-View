from __future__ import annotations

from datetime import timezone
from typing import Any, cast

from sqlalchemy import delete, select

from server.contracts.chat import StructuredProbeResponse
from server.repositories.database.sqlite import SQLiteRepository
from server.repositories.schemas.models import ModelProbeResultRecord

###############################################################################
class ModelProbeResultRepository:
    """Durable native tool-contract verdicts, keyed by model and credential."""

    # -------------------------------------------------------------------------
    def __init__(self, database: SQLiteRepository) -> None:
        self._session_factory = database.session

    # -------------------------------------------------------------------------
    def get(
        self, *, provider: str, model: str, protocol: str, fingerprint: str
    ) -> StructuredProbeResponse | None:
        with self._session_factory() as session:
            record = session.execute(
                select(ModelProbeResultRecord)
                .where(ModelProbeResultRecord.provider == provider)
                .where(ModelProbeResultRecord.model == model)
                .where(ModelProbeResultRecord.protocol == protocol)
                .where(ModelProbeResultRecord.fingerprint == fingerprint)
            ).scalars().first()
            if record is None:
                return None
            return StructuredProbeResponse(
                provider=record.provider,
                model=record.model,
                protocol=record.protocol,
                status=cast(Any, record.status),
                parse_status=record.parse_status,
                duration_ms=record.duration_ms,
                checked_at=record.checked_at.replace(tzinfo=timezone.utc),
                message=record.message,
            )

    # -------------------------------------------------------------------------
    def save(self, result: StructuredProbeResponse, *, fingerprint: str) -> None:
        """Store one verdict and drop stale verdicts of the same model."""

        if result.checked_at is None:
            raise ValueError("A persisted probe result requires a check time.")
        checked_at = result.checked_at.astimezone(timezone.utc).replace(tzinfo=None)
        with self._session_factory() as session:
            session.execute(
                delete(ModelProbeResultRecord)
                .where(ModelProbeResultRecord.provider == result.provider)
                .where(ModelProbeResultRecord.model == result.model)
            )
            session.add(
                ModelProbeResultRecord(
                    provider=result.provider,
                    model=result.model,
                    protocol=result.protocol,
                    fingerprint=fingerprint,
                    status=result.status,
                    parse_status=result.parse_status,
                    duration_ms=result.duration_ms,
                    message=result.message,
                    checked_at=checked_at,
                )
            )
            session.commit()

    # -------------------------------------------------------------------------
    def discard(self, *, provider: str, model: str) -> None:
        with self._session_factory() as session:
            session.execute(
                delete(ModelProbeResultRecord)
                .where(ModelProbeResultRecord.provider == provider)
                .where(ModelProbeResultRecord.model == model)
            )
            session.commit()
