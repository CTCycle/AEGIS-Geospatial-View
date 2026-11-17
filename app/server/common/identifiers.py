"""Stable identifiers shared by native agent boundaries."""

from __future__ import annotations

import re
import unicodedata

# "46.0037, 8.9511": a bare latitude/longitude pair (bounds checked separately).
COORDINATE_PAIR_RE = re.compile(
    r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*[,;\s]\s*"
    r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*$"
)
_DEGREES = r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)"
LABELED_COORDINATE_PAIR_RE = re.compile(
    r"\b(?P<first_axis>latitude|longitude|lat|lon|lng)\b\s*[:=]?\s*"
    rf"(?P<first>{_DEGREES})\s*(?:[,;]\s*|\band\s+|\s+)"
    r"(?P<second_axis>latitude|longitude|lat|lon|lng)\b\s*[:=]?\s*"
    rf"(?P<second>{_DEGREES})(?!\w|\.\d)",
    re.IGNORECASE,
)


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

    if _matches(requested, key, label):
        return True
    # A parenthetical remark ("Gatineau (across from Ottawa)") is commentary
    # the geocoded label never repeats.
    plain = re.sub(r"\([^)]*\)", " ", requested)
    return plain != requested and _matches(plain, key, label)


###############################################################################
def _matches(requested: str, key: str, label: str | None) -> bool:
    point = parse_coordinate_pair(requested)
    if point is not None:
        return any(
            point == parse_coordinate_pair(candidate)
            for candidate in (key, label or "")
        )
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
            and set(target_tokens[len(name) :])
            <= set(normalize_target_key(candidate).split())
        ):
            return True
    return False


###############################################################################
def parse_coordinate_pair(value: str) -> tuple[float, float] | None:
    """Return (latitude, longitude) when ``value`` is a valid coordinate pair."""

    pair = coordinate_values(value)
    if pair is None:
        return None
    latitude, longitude = pair
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return None
    return latitude, longitude


###############################################################################
def coordinate_values(value: str) -> tuple[float, float] | None:
    """Read a complete bare or axis-labeled pair without validating bounds."""

    match = COORDINATE_PAIR_RE.fullmatch(value)
    if match is not None:
        first, second = match.groups()
        return float(first), float(second)
    match = LABELED_COORDINATE_PAIR_RE.fullmatch(value.strip())
    if match is None:
        return None
    first_latitude = match["first_axis"].casefold().startswith("lat")
    second_latitude = match["second_axis"].casefold().startswith("lat")
    if first_latitude == second_latitude:
        return None
    first, second = float(match["first"]), float(match["second"])
    return (first, second) if first_latitude else (second, first)


###############################################################################
def mentions_coordinates(value: str) -> bool:
    return (
        re.search(r"\b(?:coordinates?|latitude|longitude)\b", value, re.IGNORECASE)
        is not None
    )


__all__ = [
    "COORDINATE_PAIR_RE",
    "LABELED_COORDINATE_PAIR_RE",
    "coordinate_values",
    "location_ref_matches",
    "mentions_coordinates",
    "normalize_target_key",
    "parse_coordinate_pair",
]
