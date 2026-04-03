from __future__ import annotations

from AEGIS.server.services.vector.chroma_store import ChromaVectorStore
from AEGIS.server.services.vector.indexer import VectorIndexer


def test_vector_indexer_rebuild_creates_documents(tmp_path) -> None:
    store = ChromaVectorStore(persist_path=str(tmp_path / "vectors"))
    indexer = VectorIndexer(store=store)
    result = indexer.rebuild()
    assert result["status"] == "ok"
    assert result["indexed_documents"] > 0
    assert store.exists()
