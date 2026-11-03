from __future__ import annotations

import re
from collections.abc import Sequence

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_COUNT_CLAIM = re.compile(
    r"\b(?P<n>\d+|" + "|".join(_NUMBER_WORDS) + r"|both)\s+"
    r"(?:[a-z-]+\s+){0,2}?"
    r"(?P<noun>layers?|markers?|overlays?|pins?|places?|locations?|cities|city)\b",
    re.IGNORECASE,
)
_LAYER_NOUNS = {"layer", "layers", "overlay", "overlays"}
_COMPLETENESS = re.compile(
    r"\b(complete|completed|completely|fully|successfully|everything|"
    r"all (?:the )?requested)\b",
    re.IGNORECASE,
)
_DISCLOSURE = re.compile(
    r"\b(unavailable|could not|couldn't|unable|missing|only|partial(?:ly)?|"
    r"no data|not (?:available|completed|retrieved)|failed)\b",
    re.IGNORECASE,
)
_NEGATION = re.compile(r"(?:\bnot|n't|\bnever|\bunable to|\bno)\s+(?:\w+\s+){0,2}$", re.IGNORECASE)


# -----------------------------------------------------------------------------
def _mentions(text: str, name: str) -> bool:
    cleaned = name.strip()
    if not cleaned:
        return False
    return re.search(rf"(?<!\w){re.escape(cleaned)}(?!\w)", text, re.IGNORECASE) is not None


# -----------------------------------------------------------------------------
def check_final_answer(
    text: str,
    *,
    target_names: Sequence[str],
    other_places: Sequence[str] = (),
    layer_count: int | None = None,
    feature_count: int | None = None,
    unmet: Sequence[str] = (),
) -> list[str]:
    """Return the claims in ``text`` that the verified run facts contradict.

    ``other_places`` are places the run knows about that are not targets of
    the request; ``layer_count`` is the number of visible committed overlays
    and ``feature_count`` the number of rendered point features. Either is
    ``None`` when unknown, which skips the matching claim check.
    """

    violations: list[str] = []
    targets = {name.strip().lower() for name in target_names if name.strip()}

    if targets:
        for place in other_places:
            if place.strip().lower() not in targets and _mentions(text, place):
                violations.append(f"names '{place.strip()}', which is not a resolved target")

    for match in _COUNT_CLAIM.finditer(text):
        raw = match.group("n").lower()
        claimed = 2 if raw == "both" else int(raw) if raw.isdigit() else _NUMBER_WORDS[raw]
        verified = layer_count if match.group("noun").lower() in _LAYER_NOUNS else feature_count
        if verified is not None and claimed > verified:
            violations.append(f"claims {match.group(0)!r} but only {verified} verified")

    if unmet and not _DISCLOSURE.search(text):
        for match in _COMPLETENESS.finditer(text):
            if not _NEGATION.search(text[max(0, match.start() - 24) : match.start()]):
                violations.append(
                    f"uses completeness wording ({match.group(0)!r}) while the result is incomplete"
                )
                break

    return violations
