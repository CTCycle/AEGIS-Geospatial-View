from __future__ import annotations

import re
from typing import Any

from AEGIS.server.domain.extraction.models import (
    DisallowedPattern,
    LocationSignal,
    NormalizedIntent,
    TemporalSignal,
)

COORDINATE_RE = re.compile(r"(?P<lat>[+-]?\d{1,2}(?:\.\d+)?)\s*[, ]\s*(?P<lon>[+-]?\d{1,3}(?:\.\d+)?)")
LOCATION_PHRASE_RE = re.compile(r"\b(?:in|near|around|at)\s+([A-Za-z][A-Za-z\s'\-]{2,})", re.IGNORECASE)
COMPARATIVE_RE = re.compile(r"\b(rainiest|driest|best|most|least)\b", re.IGNORECASE)
DEICTIC_RE = re.compile(r"\b(there|that place|same place|same area)\b", re.IGNORECASE)


def detect_location_signals(user_text: str) -> list[LocationSignal]:
    signals: list[LocationSignal] = []
    for match in COORDINATE_RE.finditer(user_text):
        lat = float(match.group("lat"))
        lon = float(match.group("lon"))
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            signals.append(
                LocationSignal(
                    signal_type="coordinates",
                    raw_value=match.group(0),
                    normalized_value=match.group(0),
                    latitude=lat,
                    longitude=lon,
                    confidence=0.98,
                )
            )
    for match in LOCATION_PHRASE_RE.finditer(user_text):
        phrase = match.group(1).strip(" .")
        if not phrase:
            continue
        signals.append(
            LocationSignal(
                signal_type="address",
                raw_value=phrase,
                normalized_value=phrase,
                confidence=0.7,
            )
        )
    return signals


def detect_temporal_signals(user_text: str) -> TemporalSignal:
    lowered = user_text.lower()
    if any(token in lowered for token in ("today", "now", "current")):
        return TemporalSignal(mode="current", raw_text="current")
    if any(token in lowered for token in ("tomorrow", "forecast", "next")):
        return TemporalSignal(mode="forecast", raw_text="forecast")
    if re.search(r"\b(19\d{2}|20\d{2})\b", user_text):
        return TemporalSignal(mode="historical", raw_text="historical")
    return TemporalSignal(mode="none")


def detect_deictic_references(user_text: str) -> list[str]:
    return [match.group(1).lower() for match in DEICTIC_RE.finditer(user_text)]


def detect_disallowed_patterns(user_text: str) -> list[DisallowedPattern]:
    if not COMPARATIVE_RE.search(user_text):
        return []
    return [
        DisallowedPattern(
            pattern_id="comparative_superlative",
            reason="Comparative ranking requests are outside supported deterministic scope.",
            matched_text=COMPARATIVE_RE.search(user_text).group(0),
        )
    ]


def _classify_task(user_text: str) -> str:
    lowered = user_text.lower()
    if any(token in lowered for token in ("coordinates", "latitude", "longitude", "where is")):
        return "direct_query"
    if any(token in lowered for token in ("show", "map", "overlay", "traffic", "rain", "air quality", "weather")):
        return "map_search"
    if "?" in user_text:
        return "general_question"
    return "unclear"


def _intent_from_text(user_text: str) -> NormalizedIntent:
    lowered = user_text.lower()
    if "air quality" in lowered:
        return NormalizedIntent(
            intent_id="air_quality",
            intent_label="Air quality",
            task_tags=["environment"],
            intent_tags=["air quality"],
        )
    if any(token in lowered for token in ("weather", "rain", "precipitation")):
        return NormalizedIntent(
            intent_id="weather",
            intent_label="Weather",
            task_tags=["environment"],
            intent_tags=["weather", "precipitation"],
        )
    if any(token in lowered for token in ("coordinates", "latitude", "longitude", "where is")):
        return NormalizedIntent(
            intent_id="location_lookup",
            intent_label="Location lookup",
            task_tags=["direct_query"],
            intent_tags=["coordinates", "geocode"],
        )
    if "poi" in lowered or "amenit" in lowered:
        return NormalizedIntent(
            intent_id="poi",
            intent_label="Nearby places",
            task_tags=["mobility"],
            intent_tags=["poi", "amenities"],
        )
    return NormalizedIntent(
        intent_id="general_map",
        intent_label="General map request",
        task_tags=["map"],
        intent_tags=["map"],
    )


def merge_symbolic_and_model_output(user_text: str, model_output: dict[str, Any] | None = None) -> tuple[str, NormalizedIntent]:
    _ = model_output
    return _classify_task(user_text), _intent_from_text(user_text)
