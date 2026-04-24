from __future__ import annotations

from AEGIS.server.services.vector.chroma_store import _sanitize_metadata


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
