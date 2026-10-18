"""Stable identifiers shared by native agent boundaries."""

from __future__ import annotations

import re
import unicodedata


###############################################################################
def normalize_target_key(value: str) -> str:
    """Return a punctuation- and accent-insensitive target identity."""

    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_text = re.sub(r"(?<=[A-Za-z0-9])\.(?=[A-Za-z0-9])", "", ascii_text)
    ascii_text = re.sub(r"[^A-Za-z0-9]+", " ", ascii_text)
    return " ".join(ascii_text.casefold().split())


###############################################################################
def location_ref_matches(requested: str, key: str, label: str | None) -> bool:
    """A resolved location answers to its reference key and its resolved label."""

    target = normalize_target_key(requested)
    return bool(target) and target in {
        normalize_target_key(key),
        normalize_target_key(label or ""),
    }


__all__ = ["location_ref_matches", "normalize_target_key"]
