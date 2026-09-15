"""Stable identifiers shared by native agent boundaries."""

from __future__ import annotations

import re
import unicodedata


def normalize_target_key(value: str) -> str:
    """Return a punctuation- and accent-insensitive target identity."""

    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_text = re.sub(r"(?<=[A-Za-z0-9])\.(?=[A-Za-z0-9])", "", ascii_text)
    ascii_text = re.sub(r"[^A-Za-z0-9]+", " ", ascii_text)
    return " ".join(ascii_text.casefold().split())


__all__ = ["normalize_target_key"]
