from __future__ import annotations

from server.services.llm.ollama_capability_cache import OllamaToolCapabilityCache


###############################################################################
def test_cache_hit_before_ttl_expiry() -> None:
    cache = OllamaToolCapabilityCache(ttl_seconds=10.0)
    cache.set("http://localhost:11434", "llama3.2", True, now=100.0)
    assert cache.get("http://localhost:11434", "llama3.2", now=105.0) is True


###############################################################################
def test_cache_expires_after_ttl() -> None:
    cache = OllamaToolCapabilityCache(ttl_seconds=5.0)
    cache.set("http://localhost:11434", "llama3.2", False, now=100.0)
    assert cache.get("http://localhost:11434", "llama3.2", now=106.0) is None


###############################################################################
def test_models_do_not_share_cache_records() -> None:
    cache = OllamaToolCapabilityCache(ttl_seconds=20.0)
    cache.set("http://localhost:11434", "model-a", True, now=100.0)
    cache.set("http://localhost:11434", "model-b", False, now=100.0)
    assert cache.get("http://localhost:11434", "model-a", now=101.0) is True
    assert cache.get("http://localhost:11434", "model-b", now=101.0) is False


###############################################################################
def test_base_urls_do_not_share_cache_records() -> None:
    cache = OllamaToolCapabilityCache(ttl_seconds=20.0)
    cache.set("http://localhost:11434", "llama3.2", True, now=100.0)
    cache.set("http://127.0.0.1:11434", "llama3.2", False, now=100.0)
    assert cache.get("http://localhost:11434", "llama3.2", now=101.0) is True
    assert cache.get("http://127.0.0.1:11434", "llama3.2", now=101.0) is False
