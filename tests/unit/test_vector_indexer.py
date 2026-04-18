from __future__ import annotations

import json

from AEGIS.server.services.vector.chroma_store import ChromaVectorStore
from AEGIS.server.services.vector.indexer import VectorIndexer


class _ManifestLoaderStub:
    def load_all(self):  # noqa: ANN001
        return {
            "providers": [],
            "basemaps": [
                {
                    "id": "osm_default",
                    "name": "OpenStreetMap",
                    "provider": "fallback",
                    "type": "tile",
                    "description": "Street basemap for general location context.",
                    "capabilities": ["roads"],
                    "coverage": "global",
                    "version": 1,
                    "last_modified": "2026-04-01T00:00:00Z",
                    "source_filename": "osm_default.json",
                    "source_path": "/tmp/basemaps/osm_default.json",
                    "metadata": {
                        "keywords": ["street", "city"],
                        "intent_tags": ["routing"],
                        "task_tags": ["orientation"],
                        "map_type_tags": ["street"],
                        "human_summary": "Default city street basemap.",
                        "primary_use_cases": ["city orientation"],
                        "search_examples": ["show streets in Rome"],
                        "disambiguation_notes": ["Use satellite for terrain texture."],
                        "location_dependency": "Location-specific visual context.",
                        "integration_requirements": ["No API key required"],
                        "embedding_provider": "ollama",
                    },
                }
            ],
            "overlays": [
                {
                    "id": "openaq_air_quality",
                    "name": "OpenAQ Air Quality",
                    "provider": "openaq",
                    "type": "overlay",
                    "description": "Air quality overlay for pollution insights.",
                    "capabilities": ["air quality"],
                    "coverage": "global",
                    "version": 1,
                    "last_modified": "2026-04-01T00:00:00Z",
                    "source_filename": "openaq_air_quality.json",
                    "source_path": "/tmp/overlays/openaq_air_quality.json",
                    "metadata": {
                        "keywords": ["air", "quality"],
                        "intent_tags": ["air-quality"],
                        "task_tags": ["environmental context"],
                        "map_type_tags": ["thematic"],
                        "human_summary": "Air-quality overlay for station-level pollution context.",
                        "primary_use_cases": ["pollution checks"],
                        "search_examples": ["show air quality in Rome"],
                        "disambiguation_notes": [
                            "Prefer forecast layers for future projections."
                        ],
                        "location_dependency": "Location-dependent and data-availability dependent.",
                        "integration_requirements": ["No API key required"],
                        "embedding_provider": "ollama",
                    },
                },
            ],
        }

    root_path = "/tmp/manifests"


class _EmbeddingFactoryStub:
    def normalize_provider(self, provider):  # noqa: ANN001
        _ = provider
        return "ollama"

    def resolve_default_model(self, provider):  # noqa: ANN001
        _ = provider
        return "stub-embedding-model"

    def get_embedding(
        self, *, provider: str, input_text: str, model: str | None = None
    ):  # noqa: ANN001
        _ = provider
        _ = input_text
        return [0.1, 0.2, 0.3], model or "stub-embedding-model"


def _build_memory_store(tmp_path) -> ChromaVectorStore:  # noqa: ANN001
    store = ChromaVectorStore(persist_path=str(tmp_path / "vectors"))
    store._client = None
    store._collection = None
    return store


def test_bootstrap_if_missing_rebuilds_when_artifacts_missing(tmp_path) -> None:
    store = _build_memory_store(tmp_path)
    indexer = VectorIndexer(
        store=store,
        manifest_loader=_ManifestLoaderStub(),
        embedding_factory=_EmbeddingFactoryStub(),
    )
    result = indexer.bootstrap_if_missing()
    assert result is not None
    assert result["status"] == "ok"
    metadata_path = tmp_path / "vectors" / "manifest_index_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["index_schema_version"] == 3
    assert metadata["manifest_count"] == 2
    assert metadata["chunk_count"] == 2
    assert metadata["chunking_strategy"] == "one_manifest_per_chunk"
    assert metadata["document_id_strategy"] == "kind_prefixed_manifest_id"
    assert "manifest_versions_summary" in metadata
    assert metadata["last_update_timestamp"]
    assert metadata["embedding_model"] == "stub-embedding-model"


def test_bootstrap_if_missing_skips_when_collection_and_metadata_exist(
    tmp_path, monkeypatch
) -> None:
    store = _build_memory_store(tmp_path)
    indexer = VectorIndexer(
        store=store,
        manifest_loader=_ManifestLoaderStub(),
        embedding_factory=_EmbeddingFactoryStub(),
    )
    indexer.rebuild()
    monkeypatch.setattr(
        indexer,
        "rebuild",
        lambda: (_ for _ in ()).throw(AssertionError("rebuild should not run")),
    )
    assert indexer.bootstrap_if_missing() is None


def test_bootstrap_if_missing_rebuilds_when_metadata_invalid(
    tmp_path, monkeypatch
) -> None:
    store = _build_memory_store(tmp_path)
    indexer = VectorIndexer(
        store=store,
        manifest_loader=_ManifestLoaderStub(),
        embedding_factory=_EmbeddingFactoryStub(),
    )
    indexer.rebuild()
    metadata_path = tmp_path / "vectors" / "manifest_index_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["index_schema_version"] = 1
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    called = {"value": False}
    original_rebuild = indexer.rebuild

    def tracked_rebuild():  # noqa: ANN202
        called["value"] = True
        return original_rebuild()

    monkeypatch.setattr(indexer, "rebuild", tracked_rebuild)
    result = indexer.bootstrap_if_missing()
    assert called["value"] is True
    assert result is not None
