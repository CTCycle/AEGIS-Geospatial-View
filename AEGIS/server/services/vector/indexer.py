from __future__ import annotations

from typing import Any

from AEGIS.server.services.geospatial.manifest_loader import GeospatialManifestLoader
from AEGIS.server.services.vector.chroma_store import ChromaVectorStore, VectorDocument


class VectorIndexer:
    def __init__(
        self,
        *,
        manifest_loader: GeospatialManifestLoader | None = None,
        store: ChromaVectorStore | None = None,
    ) -> None:
        self.manifest_loader = manifest_loader or GeospatialManifestLoader()
        self.store = store or ChromaVectorStore()

    def _entry_to_document(self, entry: dict[str, Any]) -> VectorDocument:
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
            ]
        ).strip()
        return VectorDocument(
            id=str(entry["id"]),
            text=text,
            metadata={
                "id": entry.get("id"),
                "name": entry.get("name"),
                "provider": entry.get("provider"),
                "type": entry.get("type"),
                "capabilities": ",".join(str(item) for item in entry.get("capabilities", [])),
                "coverage": entry.get("coverage"),
                "keywords": ",".join(str(item) for item in keywords),
            },
        )

    def rebuild(self) -> dict[str, Any]:
        catalog = self.manifest_loader.load_all()
        self.store.clear()
        documents: list[VectorDocument] = []
        for key in ("providers", "basemaps", "overlays"):
            for entry in catalog[key]:
                documents.append(self._entry_to_document(entry))
        self.store.add_documents(documents)
        return {
            "status": "ok",
            "indexed_documents": len(documents),
            "vector_path": self.store.persist_path,
        }

    def ensure_index(self) -> dict[str, Any] | None:
        if self.store.exists():
            return None
        return self.rebuild()
