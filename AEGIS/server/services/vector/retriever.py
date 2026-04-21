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
        self._bootstrap_checked = False

    def _empty_result(self) -> dict[str, list[dict[str, object]]]:
        return {
            "basemaps": [],
            "overlays": [],
            "tools": [],
            "providers": [],
        }

    def _should_rebuild_after_error(self, error: Exception) -> bool:
        message = str(error).lower()
        return (
            "expecting embedding with dimension" in message
            or "embedding dimension" in message
        )

    def retrieve_candidates(
        self,
        query: str,
        *,
        top_k: int = 8,
        basemap_k: int | None = None,
        overlay_k: int | None = None,
        provider_k: int | None = None,
    ) -> dict[str, list[dict[str, object]]]:
        if not self._bootstrap_checked:
            self.indexer.bootstrap_if_missing()
            self._bootstrap_checked = True
        try:
            matches = self.store.similarity_search(query, top_k=top_k)
        except Exception as error:
            if self._should_rebuild_after_error(error):
                try:
                    self.indexer.rebuild()
                    matches = self.store.similarity_search(query, top_k=top_k)
                except Exception:
                    return self._empty_result()
            else:
                return self._empty_result()
        basemaps: list[dict[str, object]] = []
        overlays: list[dict[str, object]] = []
        tools: list[dict[str, object]] = []
        seen: set[str] = set()
        for item in matches:
            metadata = item.get("metadata", {})
            if not isinstance(metadata, dict):
                continue
            entry_id = metadata.get("id")
            if not isinstance(entry_id, str):
                continue
            if entry_id in seen:
                continue
            seen.add(entry_id)
            distance = float(item.get("distance", 0.0) or 0.0)
            score = float(item.get("score", 0.0) or 0.0)
            candidate = {
                "id": entry_id,
                "score": score,
                "distance": distance,
                "metadata": metadata,
            }
            document_kind = str(metadata.get("document_kind") or "")
            if document_kind == "basemap":
                basemaps.append(candidate)
            elif document_kind == "overlay":
                overlays.append(candidate)
            elif document_kind == "tool":
                tools.append(candidate)
        result = {
            "basemaps": self._limit_ranked(basemaps, basemap_k or top_k),
            "overlays": self._limit_ranked(overlays, overlay_k or top_k),
            "tools": self._limit_ranked(tools, top_k),
            "providers": [],
        }
        return result

    def retrieve_layers(self, query: str, *, top_k: int = 8) -> dict[str, list[str]]:
        candidates = self.retrieve_candidates(query, top_k=top_k)
        return {
            "basemap_ids": [str(item["id"]) for item in candidates["basemaps"]],
            "overlay_ids": [str(item["id"]) for item in candidates["overlays"]],
        }

    def _limit_ranked(
        self, items: list[dict[str, object]], budget: int
    ) -> list[dict[str, object]]:
        return sorted(
            items, key=lambda item: float(item.get("score", 0.0) or 0.0), reverse=True
        )[: max(1, budget)]
