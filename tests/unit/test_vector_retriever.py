from __future__ import annotations

from AEGIS.server.services.vector.chroma_store import ChromaVectorStore
from AEGIS.server.services.vector.indexer import VectorIndexer
from AEGIS.server.services.vector.retriever import VectorRetriever


def test_vector_retriever_returns_overlay_matches(tmp_path) -> None:
    store = ChromaVectorStore(persist_path=str(tmp_path / "vectors"))
    indexer = VectorIndexer(store=store)
    indexer.rebuild()
    retriever = VectorRetriever(store=store, indexer=indexer)
    matches = retriever.retrieve_candidates("air quality overlay")
    assert isinstance(matches["overlays"], list)
    overlay_ids = [str(item["id"]) for item in matches["overlays"]]
    assert "openaq_air_quality" in overlay_ids
    assert "tomtom_traffic_flow" not in [str(item["id"]) for item in matches["basemaps"]]


def test_vector_retriever_candidate_pools_are_separate(tmp_path) -> None:
    store = ChromaVectorStore(persist_path=str(tmp_path / "vectors"))
    indexer = VectorIndexer(store=store)
    indexer.rebuild()
    retriever = VectorRetriever(store=store, indexer=indexer)
    traffic = retriever.retrieve_candidates("traffic around Zurich")
    traffic_basemaps = {str(item["id"]) for item in traffic["basemaps"]}
    traffic_overlays = {str(item["id"]) for item in traffic["overlays"]}
    assert "tomtom_traffic_flow" in traffic_overlays
    assert "tomtom_traffic_flow" not in traffic_basemaps
