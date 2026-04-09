from __future__ import annotations

import json

from AEGIS.server.services.vector.chroma_store import ChromaVectorStore
from AEGIS.server.services.vector.indexer import VectorIndexer


class _ManifestLoaderStub:
    def load_all(self):  # noqa: ANN001
        return {
            "providers": [
                {
                    "id": "provider_a",
                    "name": "Provider A",
                    "provider": "provider_a",
                    "type": "provider",
                    "description": "Provider metadata",
                    "capabilities": ["catalog"],
                    "coverage": "global",
                    "version": 1,
                    "last_modified": "2026-04-01T00:00:00Z",
                    "metadata": {},
                }
            ],
            "basemaps": [
                {
                    "id": "osm_default",
                    "name": "OpenStreetMap",
                    "provider": "provider_a",
                    "type": "tile",
                    "description": "Street basemap for general location context.",
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
    def get_embedding(self, *, provider: str, input_text: str):  # noqa: ANN001
        _ = input_text
        return [0.1, 0.2, 0.3], "stub-embedding"


def _build_memory_store(tmp_path) -> ChromaVectorStore:  # noqa: ANN001
    store = ChromaVectorStore(persist_path=str(tmp_path / "vectors"))
    store._client = None
    store._collection = None
    return store


def test_vector_indexer_rebuild_creates_documents(tmp_path) -> None:
    store = _build_memory_store(tmp_path)
    indexer = VectorIndexer(
        store=store,
        manifest_loader=_ManifestLoaderStub(),
        embedding_factory=_EmbeddingFactoryStub(),
    )
    result = indexer.rebuild()
    assert result["status"] == "ok"
    assert result["indexed_documents"] > 0
    assert store.exists()
    metadata_path = tmp_path / "vectors" / "manifest_index_metadata.json"
    assert metadata_path.is_file()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["manifest_count"] == result["indexed_documents"]
    assert metadata["embedding_model"]


def test_vector_indexer_skips_rebuild_when_cache_metadata_is_valid(tmp_path, monkeypatch) -> None:
    store = _build_memory_store(tmp_path)
    indexer = VectorIndexer(
        store=store,
        manifest_loader=_ManifestLoaderStub(),
        embedding_factory=_EmbeddingFactoryStub(),
    )
    indexer.rebuild()
    monkeypatch.setattr(indexer, "rebuild", lambda: (_ for _ in ()).throw(AssertionError("rebuild should not run")))
    assert indexer.ensure_index_up_to_date() is None


def test_vector_indexer_rebuilds_when_metadata_is_missing(tmp_path) -> None:
    store = _build_memory_store(tmp_path)
    indexer = VectorIndexer(
        store=store,
        manifest_loader=_ManifestLoaderStub(),
        embedding_factory=_EmbeddingFactoryStub(),
    )
    indexer.rebuild()
    (tmp_path / "vectors" / "manifest_index_metadata.json").unlink()
    result = indexer.ensure_index_up_to_date()
    assert result is not None
    assert result["status"] == "ok"
