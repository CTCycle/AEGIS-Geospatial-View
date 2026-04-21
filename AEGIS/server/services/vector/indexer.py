from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from AEGIS.server.repositories.manifest_embeddings import ManifestEmbeddingsRepository
from AEGIS.server.services.geospatial.manifest_loader import GeospatialManifestLoader
from AEGIS.server.services.vector.chroma_store import ChromaVectorStore, VectorDocument
from AEGIS.server.services.vector.embedding_factory import EmbeddingFactory
from AEGIS.server.services.vector.manifest_preparation import ManifestPreparationService


class VectorIndexer:
    METADATA_FILENAME = "manifest_index_metadata.json"
    INDEX_SCHEMA_VERSION = 4
    SEARCHABLE_KINDS = ("basemaps", "overlays", "tools")

    def __init__(
        self,
        *,
        manifest_loader: GeospatialManifestLoader | None = None,
        store: ChromaVectorStore | None = None,
        embeddings_repo: ManifestEmbeddingsRepository | None = None,
        embedding_factory: EmbeddingFactory | None = None,
        manifest_preparation: ManifestPreparationService | None = None,
    ) -> None:
        self.manifest_loader = manifest_loader or GeospatialManifestLoader()
        self.store = store or ChromaVectorStore()
        self.embeddings_repo = embeddings_repo or ManifestEmbeddingsRepository()
        self.embedding_factory = embedding_factory or EmbeddingFactory()
        self.manifest_preparation = manifest_preparation or ManifestPreparationService()

    def _content_hash(self, entry: dict[str, Any]) -> str:
        payload = json.dumps(entry, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _metadata_path(self) -> str:
        return os.path.join(self.store.persist_path, self.METADATA_FILENAME)

    def _manifest_summary(
        self, catalog: dict[str, list[dict[str, Any]]]
    ) -> list[dict[str, Any]]:
        summary: list[dict[str, Any]] = []
        for kind in self.SEARCHABLE_KINDS:
            for entry in catalog.get(kind, []):
                summary.append(
                    {
                        "kind": kind[:-1],
                        "id": str(entry.get("id") or ""),
                        "version": int(entry.get("version") or 1),
                        "content_hash": self._content_hash(entry),
                    }
                )
        summary.sort(key=lambda item: (item["kind"], item["id"]))
        return summary

    def _resolve_index_embedding_settings(
        self, catalog: dict[str, list[dict[str, Any]]]
    ) -> tuple[str, str]:
        providers: set[str] = set()
        for kind in self.SEARCHABLE_KINDS:
            for entry in catalog.get(kind, []):
                metadata = dict(entry.get("metadata") or {})
                providers.add(
                    self.embedding_factory.normalize_provider(
                        metadata.get("embedding_provider")
                    )
                )
        if len(providers) > 1:
            detected = ", ".join(sorted(providers))
            raise ValueError(
                f"Mixed embedding providers are not supported in one vector index: {detected}"
            )
        provider = next(iter(providers), "ollama")
        return provider, self.embedding_factory.resolve_default_model(provider)

    def _metadata_payload(
        self,
        *,
        catalog: dict[str, list[dict[str, Any]]],
        chunk_count: int,
        embedding_provider: str,
        embedding_model: str,
        build_duration_ms: int | None = None,
    ) -> dict[str, Any]:
        summary = self._manifest_summary(catalog)
        fingerprint = hashlib.sha256(
            json.dumps(summary, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        payload = {
            "index_schema_version": self.INDEX_SCHEMA_VERSION,
            "last_update_timestamp": datetime.now(UTC).isoformat(),
            "manifest_count": len(summary),
            "chunk_count": chunk_count,
            "chunking_strategy": "one_manifest_per_chunk",
            "document_id_strategy": "kind_prefixed_manifest_id",
            "searchable_kinds": [kind[:-1] for kind in self.SEARCHABLE_KINDS],
            "embedding_provider": embedding_provider,
            "embedding_model": embedding_model,
            "manifest_fingerprint": fingerprint,
            "manifest_summary": summary,
            "source_directories": {
                "basemaps": os.path.abspath(
                    os.path.join(self.manifest_loader.root_path, "basemaps")
                ),
                "overlays": os.path.abspath(
                    os.path.join(self.manifest_loader.root_path, "overlays")
                ),
                "tools": os.path.abspath(
                    os.path.join(self.manifest_loader.root_path, "tools")
                ),
            },
        }
        if isinstance(build_duration_ms, int) and build_duration_ms >= 0:
            payload["index_build_duration_ms"] = build_duration_ms
        return payload

    def _write_metadata(
        self,
        *,
        catalog: dict[str, list[dict[str, Any]]],
        chunk_count: int,
        embedding_provider: str,
        embedding_model: str,
        build_duration_ms: int | None = None,
    ) -> None:
        os.makedirs(self.store.persist_path, exist_ok=True)
        with open(self._metadata_path(), "w", encoding="utf-8") as handle:
            json.dump(
                self._metadata_payload(
                    catalog=catalog,
                    chunk_count=chunk_count,
                    embedding_provider=embedding_provider,
                    embedding_model=embedding_model,
                    build_duration_ms=build_duration_ms,
                ),
                handle,
                indent=2,
            )

    def _read_metadata(self) -> dict[str, Any] | None:
        metadata_path = self._metadata_path()
        if not os.path.isfile(metadata_path):
            return None
        try:
            with open(metadata_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except OSError | json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def _metadata_is_valid(self, payload: dict[str, Any] | None) -> bool:
        if not isinstance(payload, dict):
            return False
        if int(payload.get("index_schema_version") or 0) != self.INDEX_SCHEMA_VERSION:
            return False
        summary = payload.get("manifest_summary")
        return isinstance(summary, list) and bool(payload.get("manifest_fingerprint"))

    def _bootstrap_artifacts_present(self) -> bool:
        return bool(self.store.exists() and self._metadata_is_valid(self._read_metadata()))

    def _entry_to_document(
        self,
        *,
        entry: dict[str, Any],
        kind: str,
        embedding_provider: str,
        embedding_model: str,
        runtime_profiles: dict[str, dict[str, Any]],
    ) -> VectorDocument:
        prepared = self.manifest_preparation.prepare_entry(
            entry=entry,
            kind=kind,
            runtime_profile=runtime_profiles.get(str(entry.get("id")), {}),
        )
        try:
            embedding_vector, _ = self.embedding_factory.get_embedding(
                provider=embedding_provider,
                model=embedding_model,
                input_text=prepared.text,
            )
        except Exception:
            embedding_vector = []
        return VectorDocument(
            id=prepared.id,
            text=prepared.text,
            metadata={
                **prepared.metadata,
                "embedding_provider": embedding_provider,
                "embedding_model": embedding_model,
            },
            embedding=embedding_vector or None,
        )

    def _index_documents(
        self,
        catalog: dict[str, list[dict[str, Any]]],
        *,
        embedding_provider: str,
        embedding_model: str,
    ) -> list[VectorDocument]:
        runtime_profiles = {
            str(item.get("capability_id")): dict(item)
            for item in catalog.get("runtime_profiles", [])
            if isinstance(item, dict)
        }
        documents: list[VectorDocument] = []
        for kind in self.SEARCHABLE_KINDS:
            for entry in catalog.get(kind, []):
                documents.append(
                    self._entry_to_document(
                        entry=entry,
                        kind=kind,
                        embedding_provider=embedding_provider,
                        embedding_model=embedding_model,
                        runtime_profiles=runtime_profiles,
                    )
                )
        return documents

    def _upsert_embedding_records(
        self,
        *,
        catalog: dict[str, list[dict[str, Any]]],
        embedding_provider: str,
        embedding_model: str,
    ) -> None:
        for kind in self.SEARCHABLE_KINDS:
            manifest_kind = kind[:-1]
            for entry in catalog.get(kind, []):
                self.embeddings_repo.upsert(
                    manifest_id=str(entry["id"]),
                    manifest_kind=manifest_kind,
                    manifest_version=int(entry.get("version") or 1),
                    content_hash=self._content_hash(entry),
                    embedding_provider=embedding_provider,
                    embedding_model=embedding_model,
                    vector_collection=self.store.collection_name,
                    vector_document_id=f"{kind}:{entry['id']}",
                )

    def rebuild(self) -> dict[str, Any]:
        started = perf_counter()
        catalog = self.manifest_loader.load_all()
        embedding_provider, embedding_model = self._resolve_index_embedding_settings(catalog)
        self.store.clear()
        documents = self._index_documents(
            catalog,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
        )
        self.store.add_documents(documents)
        self._upsert_embedding_records(
            catalog=catalog,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
        )
        self._write_metadata(
            catalog=catalog,
            chunk_count=len(documents),
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            build_duration_ms=int((perf_counter() - started) * 1000),
        )
        return {
            "status": "ok",
            "indexed_documents": len(documents),
            "vector_path": self.store.persist_path,
        }

    def bootstrap_if_missing(self) -> dict[str, Any] | None:
        if self._bootstrap_artifacts_present():
            return None
        return self.rebuild()

    def ensure_index_up_to_date(self) -> dict[str, Any] | None:
        return self.bootstrap_if_missing()

    def sync(self) -> dict[str, Any]:
        catalog = self.manifest_loader.load_all()
        updated = 0
        embedding_provider, embedding_model = self._resolve_index_embedding_settings(catalog)
        for kind in self.SEARCHABLE_KINDS:
            manifest_kind = kind[:-1]
            for entry in catalog.get(kind, []):
                content_hash = self._content_hash(entry)
                existing = self.embeddings_repo.get(
                    manifest_id=str(entry["id"]),
                    manifest_kind=manifest_kind,
                )
                if (
                    existing
                    and existing.content_hash == content_hash
                    and int(entry.get("version") or 1) == existing.manifest_version
                    and existing.embedding_provider == embedding_provider
                    and existing.embedding_model == embedding_model
                ):
                    continue
                updated += 1
        if updated > 0 or not self._metadata_is_valid(self._read_metadata()):
            return self.rebuild()
        document_count = sum(len(catalog.get(kind, [])) for kind in self.SEARCHABLE_KINDS)
        self._write_metadata(
            catalog=catalog,
            chunk_count=document_count,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
        )
        return {
            "status": "ok",
            "indexed_documents": 0,
            "vector_path": self.store.persist_path,
        }
