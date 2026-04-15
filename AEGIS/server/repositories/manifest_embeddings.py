from __future__ import annotations

from datetime import datetime

from AEGIS.server.repositories.database.backend import get_database
from AEGIS.server.repositories.queries.manifest_embeddings import select_by_manifest
from AEGIS.server.repositories.schemas import Base
from AEGIS.server.repositories.schemas.models import ManifestEmbeddingRecord


class ManifestEmbeddingsRepository:
    def __init__(self) -> None:
        backend = get_database().backend
        self._session_factory = backend.session
        Base.metadata.create_all(backend.engine)

    def get(self, *, manifest_id: str, manifest_kind: str) -> ManifestEmbeddingRecord | None:
        with self._session_factory() as session:
            return session.execute(select_by_manifest(manifest_id, manifest_kind)).scalars().first()

    def upsert(
        self,
        *,
        manifest_id: str,
        manifest_kind: str,
        manifest_version: int,
        content_hash: str,
        embedding_provider: str,
        embedding_model: str,
        vector_collection: str,
        vector_document_id: str,
    ) -> None:
        with self._session_factory() as session:
            record = session.execute(select_by_manifest(manifest_id, manifest_kind)).scalars().first()
            if record is None:
                record = ManifestEmbeddingRecord(
                    manifest_id=manifest_id,
                    manifest_kind=manifest_kind,
                    manifest_version=manifest_version,
                    content_hash=content_hash,
                    embedding_provider=embedding_provider,
                    embedding_model=embedding_model,
                    vector_collection=vector_collection,
                    vector_document_id=vector_document_id,
                    last_embedded_at=datetime.utcnow(),
                )
                session.add(record)
            else:
                record.manifest_version = manifest_version
                record.content_hash = content_hash
                record.embedding_provider = embedding_provider
                record.embedding_model = embedding_model
                record.vector_collection = vector_collection
                record.vector_document_id = vector_document_id
                record.last_embedded_at = datetime.utcnow()
            session.commit()
