from __future__ import annotations

import hashlib
import json
from datetime import datetime, UTC
from typing import Any

from AEGIS.server.configurations import server_settings
from AEGIS.server.repositories.manifest_embeddings import ManifestEmbeddingsRepository
from AEGIS.server.services.geospatial.manifest_loader import GeospatialManifestLoader
from AEGIS.server.services.vector.chroma_store import ChromaVectorStore, VectorDocument
from AEGIS.server.services.vector.embedding_factory import EmbeddingFactory


class VectorIndexer:
    def __init__(
        self,
        *,
        manifest_loader: GeospatialManifestLoader | None = None,
        store: ChromaVectorStore | None = None,
        embeddings_repo: ManifestEmbeddingsRepository | None = None,
        embedding_factory: EmbeddingFactory | None = None,
    ) -> None:
        self.manifest_loader = manifest_loader or GeospatialManifestLoader()
        self.store = store or ChromaVectorStore()
        self.embeddings_repo = embeddings_repo or ManifestEmbeddingsRepository()
        self.embedding_factory = embedding_factory or EmbeddingFactory()

    def _content_hash(self, entry: dict[str, Any]) -> str:
        payload = json.dumps(entry, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _entry_to_document(self, *, entry: dict[str, Any], kind: str) -> VectorDocument:
        metadata = dict(entry.get("metadata") or {})
        keywords = metadata.get("keywords", [])
        if not isinstance(keywords, list):
            keywords = []
        text = " ".join(
            [
                str(entry.get("id") or ""),
                str(entry.get("name") or ""),
                str(entry.get("description") or ""),
                str(entry.get("provider") or ""),
                " ".join(str(item) for item in entry.get("capabilities", [])),
                str(entry.get("coverage") or ""),
                " ".join(str(item) for item in keywords),
                " ".join(str(item) for item in metadata.get("intent_tags", [])),
                " ".join(str(item) for item in metadata.get("task_tags", [])),
                " ".join(str(item) for item in metadata.get("map_type_tags", [])),
            ]
        ).strip()
        embedding_provider = str(metadata.get("embedding_provider") or "ollama")
        try:
            embedding_vector, embedding_model = self.embedding_factory.get_embedding(
                provider=embedding_provider,
                input_text=text,
            )
        except Exception:
            embedding_vector, embedding_model = ([], server_settings.vectors.default_ollama_embedding_model)
        metadata["embedding_model"] = embedding_model
        return VectorDocument(
            id=f"{kind}:{entry['id']}",
            text=text,
            metadata={
                "id": entry.get("id"),
                "name": entry.get("name"),
                "provider": entry.get("provider"),
                "type": entry.get("type"),
                "document_kind": kind[:-1] if kind.endswith("s") else kind,
                "capabilities": ",".join(str(item) for item in entry.get("capabilities", [])),
                "coverage": entry.get("coverage"),
                "keywords": ",".join(str(item) for item in keywords),
            },
            embedding=embedding_vector or None,
        )

    def rebuild(self) -> dict[str, Any]:
        catalog = self.manifest_loader.load_all()
        self.store.clear()
        documents: list[VectorDocument] = []
        for kind in ("providers", "basemaps", "overlays"):
            for entry in catalog[kind]:
                documents.append(self._entry_to_document(entry=entry, kind=kind))
        self.store.add_documents(documents)
        now = datetime.now(UTC)
        for kind in ("providers", "basemaps", "overlays"):
            for entry in catalog[kind]:
                metadata = dict(entry.get("metadata") or {})
                self.embeddings_repo.upsert(
                    manifest_id=str(entry["id"]),
                    manifest_kind=kind[:-1],
                    manifest_version=int(entry.get("version") or 1),
                    content_hash=self._content_hash(entry),
                    embedding_provider=str(metadata.get("embedding_provider") or "ollama"),
                    embedding_model=str(metadata.get("embedding_model") or server_settings.vectors.default_ollama_embedding_model),
                    vector_collection=self.store.collection_name,
                    vector_document_id=f"{kind}:{entry['id']}",
                )
                metadata["last_embedded"] = now.isoformat()
        return {
            "status": "ok",
            "indexed_documents": len(documents),
            "vector_path": self.store.persist_path,
        }

    def ensure_index_up_to_date(self) -> dict[str, Any] | None:
        if not self.store.exists():
            return self.rebuild()
        if not server_settings.vectors.auto_sync_on_start:
            return None
        return self.sync()

    def sync(self) -> dict[str, Any]:
        catalog = self.manifest_loader.load_all()
        updated = 0
        for kind in ("providers", "basemaps", "overlays"):
            manifest_kind = kind[:-1]
            for entry in catalog[kind]:
                content_hash = self._content_hash(entry)
                existing = self.embeddings_repo.get(
                    manifest_id=str(entry["id"]),
                    manifest_kind=manifest_kind,
                )
                if existing and existing.content_hash == content_hash and int(entry.get("version") or 1) == existing.manifest_version:
                    continue
                metadata = dict(entry.get("metadata") or {})
                self.embeddings_repo.upsert(
                    manifest_id=str(entry["id"]),
                    manifest_kind=manifest_kind,
                    manifest_version=int(entry.get("version") or 1),
                    content_hash=content_hash,
                    embedding_provider=str(metadata.get("embedding_provider") or "ollama"),
                    embedding_model=str(metadata.get("embedding_model") or server_settings.vectors.default_ollama_embedding_model),
                    vector_collection=self.store.collection_name,
                    vector_document_id=f"{kind}:{entry['id']}",
                )
                updated += 1
        if updated > 0:
            return self.rebuild()
        return {
            "status": "ok",
            "indexed_documents": updated,
            "vector_path": self.store.persist_path,
        }
