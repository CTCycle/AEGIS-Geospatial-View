from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from AEGIS.server.repositories.database.backend import database
from AEGIS.server.repositories.schemas.models import ModelCredentialRecord


class CredentialRepository:
    def __init__(self) -> None:
        self._session_factory = database.backend.session

    def upsert(
        self,
        *,
        provider: str,
        label: str,
        encrypted_value: str,
        key_version: str,
    ) -> ModelCredentialRecord:
        with self._session_factory() as session:
            statement = (
                select(ModelCredentialRecord)
                .where(ModelCredentialRecord.provider == provider)
                .where(ModelCredentialRecord.label == label)
            )
            record = session.execute(statement).scalars().first()
            if record is None:
                record = ModelCredentialRecord(
                    provider=provider,
                    label=label,
                    encrypted_value=encrypted_value,
                    key_version=key_version,
                    is_active=True,
                )
                session.add(record)
            else:
                record.encrypted_value = encrypted_value
                record.key_version = key_version
                record.is_active = True
                record.updated_at = datetime.utcnow()
            session.commit()
            session.refresh(record)
            return record

    def list_active(self) -> list[ModelCredentialRecord]:
        with self._session_factory() as session:
            statement = (
                select(ModelCredentialRecord)
                .where(ModelCredentialRecord.is_active.is_(True))
                .order_by(ModelCredentialRecord.provider.asc())
                .order_by(ModelCredentialRecord.label.asc())
            )
            return list(session.execute(statement).scalars().all())

    def get_active(self, *, provider: str, label: str) -> ModelCredentialRecord | None:
        with self._session_factory() as session:
            statement = (
                select(ModelCredentialRecord)
                .where(ModelCredentialRecord.provider == provider)
                .where(ModelCredentialRecord.label == label)
                .where(ModelCredentialRecord.is_active.is_(True))
            )
            return session.execute(statement).scalars().first()

    def mark_used(self, *, provider: str, label: str) -> None:
        with self._session_factory() as session:
            statement = (
                select(ModelCredentialRecord)
                .where(ModelCredentialRecord.provider == provider)
                .where(ModelCredentialRecord.label == label)
                .where(ModelCredentialRecord.is_active.is_(True))
            )
            record = session.execute(statement).scalars().first()
            if record is None:
                return
            record.last_used_at = datetime.utcnow()
            record.updated_at = datetime.utcnow()
            session.commit()
