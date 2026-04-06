from __future__ import annotations

from sqlalchemy import select

from AEGIS.server.repositories.schemas.models import ManifestEmbeddingRecord


def select_by_manifest(manifest_id: str, manifest_kind: str):
    return select(ManifestEmbeddingRecord).where(
        ManifestEmbeddingRecord.manifest_id == manifest_id,
        ManifestEmbeddingRecord.manifest_kind == manifest_kind,
    )
