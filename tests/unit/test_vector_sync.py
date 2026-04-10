from __future__ import annotations

import json

from AEGIS.server.services.vector.chroma_store import ChromaVectorStore
from AEGIS.server.services.vector.indexer import VectorIndexer


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
                }
            ],
        }


class _EmbeddingFactoryStub:
    def normalize_provider(self, provider):  # noqa: ANN001
        _ = provider
        return "ollama"

    def resolve_default_model(self, provider):  # noqa: ANN001
        _ = provider
        return "stub-embedding"

    def get_embedding(self, *, provider: str, input_text: str, model: str | None = None):  # noqa: ANN001
        _ = provider
        return [float(len(input_text)), 0.0, 1.0], model or "stub-embedding"


def _build_memory_store(tmp_path) -> ChromaVectorStore:  # noqa: ANN001
    store = ChromaVectorStore(persist_path=str(tmp_path / "vectors"))
    store._client = None
    store._collection = None
    return store


def test_vector_sync_is_idempotent(tmp_path) -> None:
    store = _build_memory_store(tmp_path)
    indexer = VectorIndexer(
        store=store,
        manifest_loader=_ManifestLoaderStub(),
        embedding_factory=_EmbeddingFactoryStub(),
    )
    first = indexer.rebuild()
    second = indexer.sync()
    third = indexer.bootstrap_if_missing()
    assert first["status"] == "ok"
    assert second["status"] == "ok"
    assert second["indexed_documents"] >= 0
    assert third is None
    metadata = json.loads((tmp_path / "vectors" / "manifest_index_metadata.json").read_text(encoding="utf-8"))
    assert metadata["manifest_fingerprint"]
