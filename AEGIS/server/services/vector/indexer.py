from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from typing import Any

from AEGIS.server.configurations import server_settings
from AEGIS.server.repositories.manifest_embeddings import ManifestEmbeddingsRepository
from AEGIS.server.services.geospatial.manifest_loader import GeospatialManifestLoader
from AEGIS.server.services.vector.chroma_store import ChromaVectorStore, VectorDocument
from AEGIS.server.services.vector.embedding_factory import EmbeddingFactory


class VectorIndexer:
    METADATA_FILENAME = "manifest_index_metadata.json"
    SEARCHABLE_KINDS = ("basemaps", "overlays")

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

    def _metadata_path(self) -> str:
        return os.path.join(self.store.persist_path, self.METADATA_FILENAME)

    def _normalize_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    def _compose_document_text(self, *, entry: dict[str, Any], kind: str) -> str:
        metadata = dict(entry.get("metadata") or {})
        capabilities = self._normalize_list(entry.get("capabilities"))
        keywords = self._normalize_list(metadata.get("keywords"))
        intent_tags = self._normalize_list(metadata.get("intent_tags"))
        task_tags = self._normalize_list(metadata.get("task_tags"))
        map_type_tags = self._normalize_list(metadata.get("map_type_tags"))
        kind_label = kind[:-1] if kind.endswith("s") else kind
        lines = [
            f"Resource type: {kind_label}",
            f"Name: {entry.get('name') or 'Unknown resource'}",
            f"Provider: {entry.get('provider') or 'Unknown provider'}",
            f"Description: {entry.get('description') or 'No description provided.'}",
        ]
        if capabilities:
            lines.append(f"Capabilities: {', '.join(capabilities)}")
        if entry.get("coverage"):
            lines.append(f"Coverage: {entry['coverage']}")
        if keywords:
            lines.append(f"Keywords: {', '.join(keywords)}")
        if intent_tags:
            lines.append(f"Intent tags: {', '.join(intent_tags)}")
        if task_tags:
            lines.append(f"Task tags: {', '.join(task_tags)}")
        if map_type_tags:
            lines.append(f"Map styles: {', '.join(map_type_tags)}")
        return "\n".join(lines).strip()

    def _entry_to_document(self, *, entry: dict[str, Any], kind: str) -> VectorDocument:
        metadata = dict(entry.get("metadata") or {})
        keywords = self._normalize_list(metadata.get("keywords"))
        text = self._compose_document_text(entry=entry, kind=kind)
        embedding_provider = str(metadata.get("embedding_provider") or "ollama")
        try:
            embedding_vector, embedding_model = self.embedding_factory.get_embedding(
                provider=embedding_provider,
                input_text=text,
            )
        except Exception:
            embedding_vector, embedding_model = (
                [],
                server_settings.vectors.default_ollama_embedding_model,
            )
        return VectorDocument(
            id=f"{kind}:{entry['id']}",
            text=text,
            metadata={
                "id": entry.get("id"),
                "name": entry.get("name"),
                "provider": entry.get("provider"),
                "type": entry.get("type"),
                "document_kind": kind[:-1] if kind.endswith("s") else kind,
                "capabilities": ",".join(self._normalize_list(entry.get("capabilities"))),
                "coverage": entry.get("coverage"),
                "keywords": ",".join(keywords),
                "embedding_provider": embedding_provider,
                "embedding_model": embedding_model,
            },
            embedding=embedding_vector or None,
        )

    def _manifest_summary(self, catalog: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
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

    def _resolve_embedding_settings(
        self,
        catalog: dict[str, list[dict[str, Any]]],
    ) -> tuple[str, str]:
        for kind in self.SEARCHABLE_KINDS:
            for entry in catalog.get(kind, []):
                metadata = dict(entry.get("metadata") or {})
                provider = str(metadata.get("embedding_provider") or "ollama")
                if provider == "openai":
                    model = server_settings.vectors.default_openai_embedding_model
                elif provider == "google":
                    model = server_settings.vectors.default_google_embedding_model
                else:
                    provider = "ollama"
                    model = server_settings.vectors.default_ollama_embedding_model
                return provider, model
        return "ollama", server_settings.vectors.default_ollama_embedding_model

    def _metadata_payload(
        self,
        *,
        catalog: dict[str, list[dict[str, Any]]],
        document_count: int,
    ) -> dict[str, Any]:
        summary = self._manifest_summary(catalog)
        fingerprint = hashlib.sha256(
            json.dumps(summary, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        embedding_provider, embedding_model = self._resolve_embedding_settings(catalog)
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "manifest_count": len(summary),
            "indexed_document_count": document_count,
            "embedding_provider": embedding_provider,
            "embedding_model": embedding_model,
            "manifest_summary": {
                "fingerprint": fingerprint,
                "items": summary,
            },
        }

    def _write_metadata(
        self,
        *,
        catalog: dict[str, list[dict[str, Any]]],
        document_count: int,
    ) -> None:
        os.makedirs(self.store.persist_path, exist_ok=True)
        with open(self._metadata_path(), "w", encoding="utf-8") as handle:
            json.dump(
                self._metadata_payload(catalog=catalog, document_count=document_count),
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
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _metadata_is_valid(self, payload: dict[str, Any] | None) -> bool:
        if not isinstance(payload, dict):
            return False
        summary = payload.get("manifest_summary")
        if not isinstance(summary, dict):
            return False
        required_fields = {
            "generated_at",
            "manifest_count",
            "embedding_provider",
            "embedding_model",
        }
        if not required_fields.issubset(payload):
            return False
        items = summary.get("items")
        if not isinstance(items, list):
            return False
        manifest_count = payload.get("manifest_count")
        if not isinstance(manifest_count, int) or manifest_count != len(items):
            return False
        return isinstance(summary.get("fingerprint"), str) and bool(summary["fingerprint"].strip())

    def _index_documents(self, catalog: dict[str, list[dict[str, Any]]]) -> list[VectorDocument]:
        documents: list[VectorDocument] = []
        for kind in self.SEARCHABLE_KINDS:
            for entry in catalog.get(kind, []):
                documents.append(self._entry_to_document(entry=entry, kind=kind))
        return documents

    def rebuild(self) -> dict[str, Any]:
        catalog = self.manifest_loader.load_all()
        self.store.clear()
        documents = self._index_documents(catalog)
        self.store.add_documents(documents)
        for kind in self.SEARCHABLE_KINDS:
            for entry in catalog.get(kind, []):
                metadata = dict(entry.get("metadata") or {})
                document_id = f"{kind}:{entry['id']}"
                embedding_provider = (
                    documents[0].metadata.get("embedding_provider")
                    if documents
                    else str(metadata.get("embedding_provider") or "ollama")
                )
                embedding_model = next(
                    (
                        str(document.metadata.get("embedding_model"))
                        for document in documents
                        if document.id == document_id
                    ),
                    str(metadata.get("embedding_model") or server_settings.vectors.default_ollama_embedding_model),
                )
                self.embeddings_repo.upsert(
                    manifest_id=str(entry["id"]),
                    manifest_kind=kind[:-1],
                    manifest_version=int(entry.get("version") or 1),
                    content_hash=self._content_hash(entry),
                    embedding_provider=str(metadata.get("embedding_provider") or embedding_provider),
                    embedding_model=embedding_model,
                    vector_collection=self.store.collection_name,
                    vector_document_id=document_id,
                )
        self._write_metadata(catalog=catalog, document_count=len(documents))
        return {
            "status": "ok",
            "indexed_documents": len(documents),
            "vector_path": self.store.persist_path,
        }

    def ensure_index_up_to_date(self) -> dict[str, Any] | None:
        metadata = self._read_metadata()
        if not self.store.exists() or not self._metadata_is_valid(metadata):
            return self.rebuild()
        return None

    def sync(self) -> dict[str, Any]:
        catalog = self.manifest_loader.load_all()
        updated = 0
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
                ):
                    continue
                updated += 1
        if updated > 0 or not self._metadata_is_valid(self._read_metadata()):
            return self.rebuild()
        document_count = sum(len(catalog.get(kind, [])) for kind in self.SEARCHABLE_KINDS)
        self._write_metadata(catalog=catalog, document_count=document_count)
        return {
            "status": "ok",
            "indexed_documents": 0,
            "vector_path": self.store.persist_path,
        }
