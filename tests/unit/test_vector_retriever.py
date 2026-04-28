from __future__ import annotations

from AEGIS.server.services.vector.chroma_store import ChromaVectorStore
from AEGIS.server.services.vector.indexer import VectorIndexer
from AEGIS.server.services.vector.retriever import VectorRetriever


class _ManifestLoaderStub:
    root_path = "/tmp/manifests"

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
                    "metadata": {
                        "keywords": ["street", "city"],
                        "intent_tags": ["routing"],
                        "task_tags": ["orientation"],
                        "map_type_tags": ["street"],
                        "human_summary": "Default city basemap.",
                        "primary_use_cases": ["city context"],
                        "search_examples": ["show roads in Zurich"],
                        "disambiguation_notes": [
                            "Use satellite for imagery-first tasks."
                        ],
                        "location_dependency": "Location-specific context.",
                        "integration_requirements": ["No API key required"],
                    },
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
                    "metadata": {
                        "keywords": ["air", "quality"],
                        "intent_tags": ["air-quality"],
                        "task_tags": ["pollution checks"],
                        "map_type_tags": ["thematic"],
                        "human_summary": "Station-based air-quality layer.",
                        "primary_use_cases": ["air quality awareness"],
                        "search_examples": ["show air quality in Zurich"],
                        "disambiguation_notes": [
                            "Use aerosol imagery for broad atmospheric patterns."
                        ],
                        "location_dependency": "Location-specific and data-dependent.",
                        "integration_requirements": ["No API key required"],
                    },
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
                    "metadata": {
                        "keywords": ["traffic", "roads"],
                        "intent_tags": ["traffic"],
                        "task_tags": ["congestion monitoring"],
                        "map_type_tags": ["thematic"],
                        "human_summary": "Traffic flow overlay for congestion context.",
                        "primary_use_cases": ["traffic checks"],
                        "search_examples": ["show traffic in Zurich"],
                        "disambiguation_notes": [
                            "Requires live traffic-capable provider."
                        ],
                        "location_dependency": "Location-specific and near real-time.",
                        "integration_requirements": ["Provider integration required"],
                    },
                },
            ],
        }


class _EmbeddingFactoryStub:
    def normalize_provider(self, provider):  # noqa: ANN001
        _ = provider
        return "ollama"

    def resolve_default_model(self, provider):  # noqa: ANN001
        _ = provider
        return "stub-embedding"

    def get_embedding(
        self, *, provider: str, input_text: str, model: str | None = None
    ):  # noqa: ANN001
        _ = provider
        return [float(len(input_text)), 0.0, 1.0], model or "stub-embedding"


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
    assert "tomtom_traffic_flow" not in [
        str(item["id"]) for item in matches["basemaps"]
    ]
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


def test_vector_retriever_raw_prompt_finds_thematic_overlay(tmp_path) -> None:
    store = _build_memory_store(tmp_path)
    indexer = VectorIndexer(
        store=store,
        manifest_loader=_ManifestLoaderStub(),
        embedding_factory=_EmbeddingFactoryStub(),
    )
    indexer.rebuild()
    retriever = VectorRetriever(store=store, indexer=indexer)
    matches = retriever.retrieve_candidates("show traffic around Zurich", top_k=6)
    assert "tomtom_traffic_flow" in [str(item["id"]) for item in matches["overlays"]]


def test_vector_retriever_rebuilds_after_dimension_mismatch(
    tmp_path, monkeypatch
) -> None:
    store = _build_memory_store(tmp_path)
    indexer = VectorIndexer(
        store=store,
        manifest_loader=_ManifestLoaderStub(),
        embedding_factory=_EmbeddingFactoryStub(),
    )
    indexer.rebuild()
    retriever = VectorRetriever(store=store, indexer=indexer)

    call_count = {"count": 0}
    original_similarity_search = store.similarity_search

    def flaky_similarity_search(query_text, *, top_k=5):  # noqa: ANN001
        call_count["count"] += 1
        if call_count["count"] == 1:
            raise RuntimeError(
                "Collection expecting embedding with dimension of 768, got 384"
            )
        return original_similarity_search(query_text, top_k=top_k)

    rebuild_calls = {"count": 0}
    original_rebuild = indexer.rebuild

    def tracked_rebuild():  # noqa: ANN202
        rebuild_calls["count"] += 1
        return original_rebuild()

    monkeypatch.setattr(store, "similarity_search", flaky_similarity_search)
    monkeypatch.setattr(indexer, "rebuild", tracked_rebuild)

    matches = retriever.retrieve_candidates("air quality overlay")

    assert rebuild_calls["count"] == 1
    assert call_count["count"] == 2
    assert "openaq_air_quality" in [str(item["id"]) for item in matches["overlays"]]


def test_vector_retriever_returns_empty_candidates_when_search_fails(
    tmp_path, monkeypatch
) -> None:
    store = _build_memory_store(tmp_path)
    indexer = VectorIndexer(
        store=store,
        manifest_loader=_ManifestLoaderStub(),
        embedding_factory=_EmbeddingFactoryStub(),
    )
    indexer.rebuild()
    retriever = VectorRetriever(store=store, indexer=indexer)

    monkeypatch.setattr(
        store,
        "similarity_search",
        lambda query_text, *, top_k=5: (_ for _ in ()).throw(
            RuntimeError("store offline")
        ),
    )

    matches = retriever.retrieve_candidates("air quality overlay")

    assert matches == {"basemaps": [], "overlays": [], "providers": [], "tools": []}
