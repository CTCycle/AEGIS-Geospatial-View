from __future__ import annotations

from AEGIS.server.services.vector.chroma_store import ChromaVectorStore
from AEGIS.server.services.vector.indexer import VectorIndexer
from AEGIS.server.services.vector.retriever import VectorRetriever


def test_vector_retriever_returns_overlay_matches(tmp_path) -> None:
    store = ChromaVectorStore(persist_path=str(tmp_path / "vectors"))
    indexer = VectorIndexer(store=store)
    indexer.rebuild()
    retriever = VectorRetriever(store=store, indexer=indexer)
    matches = retriever.retrieve_layers("air quality overlay")
    assert isinstance(matches["overlay_ids"], list)
    assert "openaq_air_quality" in matches["overlay_ids"]
