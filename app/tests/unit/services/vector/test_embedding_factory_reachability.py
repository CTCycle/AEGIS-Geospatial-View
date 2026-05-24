from __future__ import annotations

from urllib.error import URLError

from server.services.vector.embedding_factory import EmbeddingFactory


def test_is_ollama_reachable_handles_url_errors(monkeypatch) -> None:
    factory = EmbeddingFactory()
    factory._ollama_reachable = None

    def _raise_url_error(*args, **kwargs):  # noqa: ANN002, ANN003
        raise URLError("unreachable")

    monkeypatch.setattr("server.services.vector.embedding_factory.urlopen", _raise_url_error)

    assert factory._is_ollama_reachable() is False
