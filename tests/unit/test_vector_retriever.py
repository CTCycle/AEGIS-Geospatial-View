from __future__ import annotations

from AEGIS.server.services.vector.chroma_store import ChromaVectorStore
from AEGIS.server.services.vector.indexer import VectorIndexer
from AEGIS.server.services.vector.retriever import VectorRetriever


class _ManifestLoaderStub:
    def load_all(self):  # noqa: ANN001
        return {
            "providers": [],
            "basemaps": [
                {
                    "id": "osm_default",
                    "name": "OpenStreetMap",
                    "provider": "provider_a",
                    "type": "tile",
                    "description": "Street basemap for city context.",
                    "capabilities": ["roads"],
                    "coverage": "global",
                    "version": 1,
                    "last_modified": "2026-04-01T00:00:00Z",
                    "metadata": {"keywords": ["street", "city"]},
                }
            ],
            "overlays": [
                {
                    "id": "openaq_air_quality",
                    "name": "OpenAQ Air Quality",
                    "provider": "provider_a",
                    "type": "overlay",
                    "description": "Air quality overlay for pollution insights.",
                    "capabilities": ["air quality"],
                    "coverage": "global",
                    "version": 1,
                    "last_modified": "2026-04-01T00:00:00Z",
                    "metadata": {"keywords": ["air", "quality"]},
                },
                {
                    "id": "tomtom_traffic_flow",
                    "name": "TomTom Traffic Flow",
                    "provider": "provider_a",
                    "type": "overlay",
                    "description": "Traffic flow overlay for congestion analysis.",
                    "capabilities": ["traffic"],
                    "coverage": "urban",
                    "version": 1,
                    "last_modified": "2026-04-01T00:00:00Z",
                    "metadata": {"keywords": ["traffic", "roads"]},
                }
            ],
        }


class _EmbeddingFactoryStub:
    def get_embedding(self, *, provider: str, input_text: str):  # noqa: ANN001
        _ = provider
        return [float(len(input_text)), 0.0, 1.0], "stub-embedding"


def _build_memory_store(tmp_path) -> ChromaVectorStore:  # noqa: ANN001
    store = ChromaVectorStore(persist_path=str(tmp_path / "vectors"))
    store._client = None
    store._collection = None
    return store


def test_vector_retriever_returns_overlay_matches(tmp_path) -> None:
    store = _build_memory_store(tmp_path)
    indexer = VectorIndexer(
        store=store,
        manifest_loader=_ManifestLoaderStub(),
        embedding_factory=_EmbeddingFactoryStub(),
    )
    indexer.rebuild()
    retriever = VectorRetriever(store=store, indexer=indexer)
    matches = retriever.retrieve_candidates("air quality overlay")
    assert isinstance(matches["overlays"], list)
    overlay_ids = [str(item["id"]) for item in matches["overlays"]]
    assert "openaq_air_quality" in overlay_ids
    assert all("score" in item for item in matches["overlays"])
    assert "tomtom_traffic_flow" not in [str(item["id"]) for item in matches["basemaps"]]
    assert matches["providers"] == []


def test_vector_retriever_candidate_pools_are_separate(tmp_path) -> None:
    store = _build_memory_store(tmp_path)
    indexer = VectorIndexer(
        store=store,
        manifest_loader=_ManifestLoaderStub(),
        embedding_factory=_EmbeddingFactoryStub(),
    )
    indexer.rebuild()
    retriever = VectorRetriever(store=store, indexer=indexer)
    traffic = retriever.retrieve_candidates("traffic around Zurich")
    traffic_basemaps = {str(item["id"]) for item in traffic["basemaps"]}
    traffic_overlays = {str(item["id"]) for item in traffic["overlays"]}
    assert "tomtom_traffic_flow" in traffic_overlays
    assert "tomtom_traffic_flow" not in traffic_basemaps
