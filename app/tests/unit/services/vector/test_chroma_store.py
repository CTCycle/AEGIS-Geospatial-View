from __future__ import annotations

import os
import shutil
from pathlib import Path

from server.services.vector.chroma_store import _sanitize_metadata
from server.services.vector.chroma_store import ChromaVectorStore


def test_sanitize_metadata_converts_nested_values_to_chroma_safe_scalars() -> None:
    sanitized = _sanitize_metadata(
        {
            "id": "x",
            "enabled": True,
            "weight": 1.25,
            "tags": ["a", "b"],
            "details": {"k": "v"},
            "none_value": None,
        }
    )
    assert sanitized["id"] == "x"
    assert sanitized["enabled"] is True
    assert sanitized["weight"] == 1.25
    assert isinstance(sanitized["tags"], str)
    assert isinstance(sanitized["details"], str)
    assert sanitized["none_value"] == ""


def test_chroma_store_sets_local_cache_env_defaults(monkeypatch) -> None:
    tmp_path = Path(
        "G:/Projects/Repositories/Web applications/AEGIS Geospatial View/.tmp_test_chroma_store"
    )
    if tmp_path.exists():
        shutil.rmtree(tmp_path)
    tmp_path.mkdir(parents=True)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.delenv("CHROMA_CACHE_DIR", raising=False)
    monkeypatch.setattr(
        "server.services.vector.chroma_store.PROJECT_DIR",
        str(tmp_path),
    )
    ChromaVectorStore(persist_path=str(tmp_path / "vectors"))
    assert os.environ.get("XDG_CACHE_HOME") == str(tmp_path / ".cache")
    assert os.environ.get("CHROMA_CACHE_DIR") == str(tmp_path / ".cache" / "chroma")


def test_chroma_store_accepts_path_persist_path(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "existing-cache"))
    monkeypatch.setenv("CHROMA_CACHE_DIR", str(tmp_path / "existing-cache" / "chroma"))

    store = ChromaVectorStore(persist_path=tmp_path / "vectors")
    store._client = None
    store._collection = None

    assert store.persist_path == str(tmp_path / "vectors")
    assert (tmp_path / "vectors").is_dir()
