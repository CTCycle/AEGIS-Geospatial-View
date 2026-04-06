from __future__ import annotations

from AEGIS.server.services.vector.chroma_store import ChromaVectorStore
from AEGIS.server.services.vector.indexer import VectorIndexer


def test_vector_sync_is_idempotent(tmp_path) -> None:
    store = ChromaVectorStore(persist_path=str(tmp_path / "vectors"))
    indexer = VectorIndexer(store=store)
    first = indexer.rebuild()
    second = indexer.sync()
    assert first["status"] == "ok"
    assert second["status"] == "ok"
    assert second["indexed_documents"] >= 0
