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
    """A resolved location answers to its reference key and its resolved label.

    The router and the model qualify the same place differently ("Springfield,
    Illinois" vs "Springfield, Illinois, United States"), so a reference also
    matches when it starts with the resolved place name and every remaining
    qualifier appears in that key or label. A parent such as "France" never
    matches a resolved "Paris, France" because the leading name differs.
    """

    target = normalize_target_key(requested)
    if not target:
        return False
    target_tokens = target.split()
    for candidate in (key, label or ""):
        if target == normalize_target_key(candidate):
            return True
        name = normalize_target_key(candidate.split(",", 1)[0]).split()
        if (
            name
            and target_tokens[: len(name)] == name
            and set(target_tokens[len(name) :]) <= set(normalize_target_key(candidate).split())
        ):
            return True
    return False


__all__ = ["location_ref_matches", "normalize_target_key"]
