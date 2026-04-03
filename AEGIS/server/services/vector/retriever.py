from __future__ import annotations

from AEGIS.server.services.vector.chroma_store import ChromaVectorStore
from AEGIS.server.services.vector.indexer import VectorIndexer


class VectorRetriever:
    def __init__(
        self,
        *,
        store: ChromaVectorStore | None = None,
        indexer: VectorIndexer | None = None,
    ) -> None:
        self.store = store or ChromaVectorStore()
        self.indexer = indexer or VectorIndexer(store=self.store)

    def retrieve_layers(self, query: str, *, top_k: int = 8) -> dict[str, list[str]]:
        self.indexer.ensure_index()
        matches = self.store.similarity_search(query, top_k=top_k)
        basemap_ids: list[str] = []
        overlay_ids: list[str] = []
        for item in matches:
            metadata = item.get("metadata", {})
            entry_id = metadata.get("id")
            entry_type = metadata.get("type")
            if not isinstance(entry_id, str):
                continue
            if entry_type == "tile" and entry_id not in basemap_ids:
                basemap_ids.append(entry_id)
            if entry_type != "provider" and entry_id not in overlay_ids:
                overlay_ids.append(entry_id)
        return {"basemap_ids": basemap_ids, "overlay_ids": overlay_ids}
