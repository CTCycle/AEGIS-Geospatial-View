from __future__ import annotations

from datetime import UTC, datetime

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy import update as sqlalchemy_update

from server.repositories.database.backend import get_database
from server.repositories.schemas.models import CredentialEncryptionMaterial

DEFAULT_KEY_PURPOSE = "credential_encryption"


###############################################################################
class CredentialEncryptionMaterialRepository:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self._session_factory = get_database().backend.session

    # -------------------------------------------------------------------------
    def ensure_seeded(
        self, purpose: str = DEFAULT_KEY_PURPOSE
    ) -> CredentialEncryptionMaterial:
        existing = self.get_active_material(purpose)
        if existing is not None:
            return existing

        now = datetime.now(UTC).replace(tzinfo=None)
        material = CredentialEncryptionMaterial(
            key_purpose=purpose,
            key_version=1,
            key_material=Fernet.generate_key().decode("utf-8"),
            is_active=True,
            seeded_at=now,
            activated_at=now,
        )
        with self._session_factory() as session:
            session.add(material)
            session.commit()
            session.refresh(material)
        return material

    # -------------------------------------------------------------------------
    def get_active_material(
        self, purpose: str = DEFAULT_KEY_PURPOSE
    ) -> CredentialEncryptionMaterial | None:
        with self._session_factory() as session:
            statement = (
                select(CredentialEncryptionMaterial)
                .where(CredentialEncryptionMaterial.key_purpose == purpose)
                .where(CredentialEncryptionMaterial.is_active.is_(True))
                .order_by(CredentialEncryptionMaterial.key_version.desc())
                .limit(1)
            )
            return session.execute(statement).scalars().first()

    # -------------------------------------------------------------------------
    def get_material_by_version(
        self, version: int, purpose: str = DEFAULT_KEY_PURPOSE
    ) -> CredentialEncryptionMaterial | None:
        with self._session_factory() as session:
            statement = (
                select(CredentialEncryptionMaterial)
                .where(CredentialEncryptionMaterial.key_purpose == purpose)
                .where(CredentialEncryptionMaterial.key_version == version)
            )
            return session.execute(statement).scalars().first()

    # -------------------------------------------------------------------------
    def rotate_material(
        self, purpose: str = DEFAULT_KEY_PURPOSE
    ) -> CredentialEncryptionMaterial:
        active = self.get_active_material(purpose)
        next_version = (active.key_version + 1) if active is not None else 1
        now = datetime.now(UTC).replace(tzinfo=None)

        with self._session_factory() as session:
            if active is not None:
                session.execute(
                    sqlalchemy_update(CredentialEncryptionMaterial)
                    .where(CredentialEncryptionMaterial.id == active.id)
                    .values(is_active=False, deactivated_at=now)
                )

            material = CredentialEncryptionMaterial(
                key_purpose=purpose,
                key_version=next_version,
                key_material=Fernet.generate_key().decode("utf-8"),
                is_active=True,
                seeded_at=now,
                activated_at=now,
            )
            session.add(material)
            session.commit()
            session.refresh(material)
        return material


###############################################################################
def seed_credential_encryption_material() -> CredentialEncryptionMaterial:
    return CredentialEncryptionMaterialRepository().ensure_seeded()
