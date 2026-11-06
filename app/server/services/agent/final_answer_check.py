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
# A count of mapped records ("all 205 events", "25 features") claimed in a
# sentence that says it is on the map. The number may not exceed what rendered.
_MAP_ITEM_CLAIM = re.compile(
    r"(?<!\bof )(?<!\bof the )(?<!\bout of )\b(?P<n>\d[\d,]*)\s+"
    r"(?:[a-z-]+\s+){0,2}?(?:events?|features?|records?|results?|points?|items?|"
    r"earthquakes?|quakes?|incidents?|sites?|stations?|observations?)\b",
    re.IGNORECASE,
)
_MAP_CONTEXT = re.compile(
    r"\b(?:map|plotted|rendered|displayed|drawn|markers?|pins?|layer)\b", re.IGNORECASE
)
_SENTENCE_BREAK = re.compile(r"(?<=[.!?;])\s+|\n+")
_COMPLETENESS = re.compile(
    r"\b(complete|completed|completely|fully|successfully|everything|"
    r"all (?:the )?requested)\b",
    re.IGNORECASE,
)
_DISCLOSURE = re.compile(
    r"\b(unavailable|could not|couldn't|unable|missing|only|partial(?:ly)?|"
    r"no data|not (?:available|completed|retrieved)|failed|ambiguous|unresolved)\b",
    re.IGNORECASE,
)
_MAP_CLAIM = re.compile(
    r"\b(?:the map (?:now )?(?:shows|displays|contains|is showing)|on the map|"
    r"map (?:overlay|layer)s?|(?:I(?:'ve| have)?|we) (?:prepared|created|built|added|drawn) (?:the |a )?map)",
    re.IGNORECASE,
)
_TRUNCATION_DISCLOSURE = re.compile(
    r"\b(?:only|limited|truncated|subset|top \d+|first \d+|cut)\b", re.IGNORECASE
)
# Numbers an answer cites with a unit that evidence can confirm.
_UNIT_NUMBER = re.compile(
    r"(?<![\w.])(?P<n>-?\d+(?:\.\d+)?)\s?(?P<unit>°\s?[CF]?|m/s|km/h|kph|mph|hPa)(?!\w)"
    r"|\b(?:magnitude\s+|(?-i:M)\s?)(?P<m>\d+(?:\.\d+)?)\b",
    re.IGNORECASE,
)
# A layer reported removed or hidden; only a committed map edit supports it.
_LAYER_EDIT_CLAIM = re.compile(
    r"\b(?:remov(?:ed|ing)|delet(?:ed|ing)|cleared|hidden|hid|taken off|turned off|switched off)\b",
    re.IGNORECASE,
)
_LAYER_WORD = re.compile(r"\b(?:layers?|overlays?)\b", re.IGNORECASE)
_ANY_NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?!\w)")
_NEGATION = re.compile(r"(?:\bnot|n't|\bnever|\bunable to|\bno)\s+(?:\w+\s+){0,2}$", re.IGNORECASE)


# -----------------------------------------------------------------------------
def _mentions(text: str, name: str) -> bool:
    cleaned = name.strip()
    if not cleaned:
        return False
    return re.search(rf"(?<!\w){re.escape(cleaned)}(?!\w)", text, re.IGNORECASE) is not None


# -----------------------------------------------------------------------------
def value_is_supported(raw: str, unit: str, evidence: Sequence[float]) -> bool:
    """Whether evidence supports a cited value: a datum, a difference or a conversion."""

    value = float(raw)
    decimals = len(raw.split(".")[1]) if "." in raw else 0
    tolerance = 0.5 * 10 ** -decimals + 1e-9
    candidates = {round(item, 6) for item in evidence}
    if unit.upper().endswith("F"):
        candidates |= {round(item * 9 / 5 + 32, 6) for item in candidates}
    if any(abs(value - item) <= tolerance for item in candidates):
        return True
    ordered = sorted(candidates)
    return any(abs(abs(a - b) - abs(value)) <= tolerance for a in ordered for b in ordered)


# -----------------------------------------------------------------------------
def _cites_any(cited: Sequence[str], values: Sequence[float]) -> bool:
    for raw in cited:
        tolerance = 0.5 * 10 ** -(len(raw.split(".")[1]) if "." in raw else 0) + 1e-9
        if any(abs(float(raw) - value) <= tolerance for value in values):
            return True
    return False

# -----------------------------------------------------------------------------
def check_final_answer(
    text: str,
    *,
    target_names: Sequence[str],
    other_places: Sequence[str] = (),
    layer_count: int | None = None,
    feature_count: int | None = None,
    unmet: Sequence[str] = (),
    unresolved_targets: Sequence[str] = (),
    required_targets: Sequence[Sequence[str]] = (),
    undelivered: Sequence[str] = (),
    map_rendered: bool | None = None,
    evidence_numbers: Sequence[float] = (),
    truncations: Sequence[tuple[int, int]] = (),
    layer_edits: int | None = None,
    cite_groups: Sequence[Sequence[float]] = (),
) -> list[str]:
    """Return the claims in ``text`` that the verified run facts contradict.

    ``other_places`` are places the run knows about that are not targets of
    the request; ``layer_count`` is the number of visible committed overlays
    and ``feature_count`` the number of rendered point features. Either is
    ``None`` when unknown, which skips the matching claim check.
    ``unresolved_targets`` are requested places no resolution answered to; an
    answer may name them only to disclose that they were not shown.
    ``required_targets`` lists, per resolved target of a multi-place request,
    the spellings that name it; an answer must name every one of them.
    ``undelivered`` describes unmet or failed obligations the answer must
    disclose; ``map_rendered`` is False when no verified map exists, so the
    answer may not describe map content; ``evidence_numbers`` are the values
    the run's data carries, which numbers cited with a unit must match; and
    ``truncations`` are (shown, total) layers whose records were cut; and
    ``layer_edits`` counts the layers the committed map-state diff removed or
    hid (``None`` skips the claim check); and ``cite_groups`` are the figures an
    analysis answer must cite: one of each group, or, for several groups, the
    difference between two of them.
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

    for sentence in _SENTENCE_BREAK.split(text):
        if not _MAP_CONTEXT.search(sentence) or _TRUNCATION_DISCLOSURE.search(sentence):
            continue
        for match in _MAP_ITEM_CLAIM.finditer(sentence):
            claimed = int(match.group("n").replace(",", ""))
            cut_total = any(claimed == total > shown for shown, total in truncations)
            if cut_total or (feature_count is not None and claimed > feature_count):
                violations.append(
                    f"claims {match.group(0)!r} on the map but the map shows "
                    f"{feature_count if feature_count is not None else 'fewer'}"
                )
                break

    for spellings in required_targets:
        if spellings and not any(_mentions(text, spelling) for spelling in spellings):
            violations.append(f"does not name the requested place '{spellings[0]}'")

    if not _DISCLOSURE.search(text):
        for name in unresolved_targets:
            if _mentions(text, name):
                violations.append(f"names '{name}' without disclosing it was not resolved")

    if unmet and not _DISCLOSURE.search(text):
        for match in _COMPLETENESS.finditer(text):
            if not _NEGATION.search(text[max(0, match.start() - 24) : match.start()]):
                violations.append(
                    f"uses completeness wording ({match.group(0)!r}) while the result is incomplete"
                )
                break

    if undelivered and not _DISCLOSURE.search(text):
        violations.append("does not disclose: " + "; ".join(undelivered))

    if map_rendered is False:
        for match in _MAP_CLAIM.finditer(text):
            if not _NEGATION.search(text[max(0, match.start() - 24) : match.start()]):
                violations.append(f"describes map content ({match.group(0)!r}) but no map was verified")
                break

    for shown, total in truncations:
        if str(total) not in text and not _TRUNCATION_DISCLOSURE.search(text):
            violations.append(f"does not disclose that the map layer shows {shown} of {total} records")

    if layer_edits == 0:
        for sentence in _SENTENCE_BREAK.split(text):
            claim = _LAYER_EDIT_CLAIM.search(sentence)
            if (
                claim
                and _LAYER_WORD.search(sentence)
                and not _NEGATION.search(sentence[max(0, claim.start() - 24) : claim.start()])
            ):
                violations.append(f"claims a layer was changed ({claim.group(0)!r}) but the map edit removed or hid none")
                break

    if evidence_numbers:
        for match in _UNIT_NUMBER.finditer(text):
            raw = match.group("n") or match.group("m")
            if not value_is_supported(raw, match.group("unit") or "", evidence_numbers):
                violations.append(f"cites {match.group(0)!r}, which the evidence does not support")
                break

    groups = [group for group in cite_groups if group]
    if groups:
        cited = _ANY_NUMBER.findall(text)
        differences = [abs(a - b) for i, first in enumerate(groups) for second in groups[i + 1 :] for a in first for b in second]
        if not all(_cites_any(cited, group) for group in groups) and not (
            len(groups) > 1 and _cites_any(cited, differences)
        ):
            violations.append("cites no value for the requested analysis although the evidence has them")

    return violations
