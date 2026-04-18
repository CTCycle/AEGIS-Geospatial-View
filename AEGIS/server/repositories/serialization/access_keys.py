from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import case, select, update

from AEGIS.server.repositories.database.backend import get_database
from AEGIS.server.repositories.schemas.models import AccessKeyRecord
from AEGIS.server.services.cryptography import (
    build_access_key_fingerprint,
    decrypt_access_key,
    encrypt_access_key,
)

SUPPORTED_PROVIDERS = {"openai", "gemini"}


###############################################################################
class AccessKeySerializer:
    def __init__(self) -> None:
        self._session_factory = get_database().backend.session

    # -------------------------------------------------------------------------
    def normalize_provider(self, provider: str) -> str:
        normalized = provider.strip().lower()
        if normalized not in SUPPORTED_PROVIDERS:
            raise ValueError("Unsupported provider")
        return normalized

    # -------------------------------------------------------------------------
    def list_keys(self, provider: str) -> list[AccessKeyRecord]:
        normalized = self.normalize_provider(provider)
        with self._session_factory() as session:
            statement = (
                select(AccessKeyRecord)
                .where(AccessKeyRecord.provider == normalized)
                .order_by(case((AccessKeyRecord.is_active.is_(True), 0), else_=1))
                .order_by(AccessKeyRecord.created_at.desc())
                .order_by(AccessKeyRecord.id.desc())
            )
            return list(session.execute(statement).scalars().all())

    # -------------------------------------------------------------------------
    def create_key(self, provider: str, plaintext_key: str) -> AccessKeyRecord:
        normalized = self.normalize_provider(provider)
        ciphertext = encrypt_access_key(plaintext_key)
        row = AccessKeyRecord(
            provider=normalized,
            encrypted_value=ciphertext,
            fingerprint=build_access_key_fingerprint(ciphertext),
            is_active=False,
        )
        with self._session_factory() as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    # -------------------------------------------------------------------------
    def activate_key(self, key_id: int, provider: str | None = None) -> AccessKeyRecord:
        normalized_provider = self.normalize_provider(provider) if provider else None
        with self._session_factory() as session:
            query = select(AccessKeyRecord).where(AccessKeyRecord.id == key_id)
            if normalized_provider:
                query = query.where(AccessKeyRecord.provider == normalized_provider)
            target = session.execute(query).scalars().first()
            if target is None:
                raise KeyError("Access key not found")

            now = datetime.now(UTC)
            session.execute(
                update(AccessKeyRecord)
                .where(AccessKeyRecord.provider == target.provider)
                .values(is_active=False, updated_at=now)
            )
            target.is_active = True
            target.updated_at = now
            session.commit()
            session.refresh(target)
            return target

    # -------------------------------------------------------------------------
    def delete_key(self, key_id: int, provider: str | None = None) -> None:
        normalized_provider = self.normalize_provider(provider) if provider else None
        with self._session_factory() as session:
            query = select(AccessKeyRecord).where(AccessKeyRecord.id == key_id)
            if normalized_provider:
                query = query.where(AccessKeyRecord.provider == normalized_provider)
            target = session.execute(query).scalars().first()
            if target is None:
                raise KeyError("Access key not found")
            session.delete(target)
            session.commit()

    # -------------------------------------------------------------------------
    def get_active_key(
        self, provider: str, mark_used: bool = False
    ) -> AccessKeyRecord | None:
        normalized = self.normalize_provider(provider)
        with self._session_factory() as session:
            statement = (
                select(AccessKeyRecord)
                .where(AccessKeyRecord.provider == normalized)
                .where(AccessKeyRecord.is_active.is_(True))
                .limit(1)
            )
            row = session.execute(statement).scalars().first()
            if row is None:
                return None
            if mark_used:
                now = datetime.now(UTC)
                row.last_used_at = now
                row.updated_at = now
                session.commit()
                session.refresh(row)
            return row

    # -------------------------------------------------------------------------
    def decrypt_for_runtime(
        self, provider: str, *, mark_used: bool = True
    ) -> str | None:
        row = self.get_active_key(provider, mark_used=mark_used)
        if row is None:
            return None
        return decrypt_access_key(row.encrypted_value)
