from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, time
from typing import Any

from AEGIS.app.api.schemas.geographics import (
    AgenticMapRequest,
    Coordinates,
    Location,
    MapRequest,
    TemporalContext,
    MIN_TIMELINE_YEAR,
)
from AEGIS.app.utils.services.geographics import (
    CITY_PRESETS,
    COUNTRY_PRESETS,
    DEFAULT_LAYER_KEY,
    LAYER_CONFIGS,
)


DEFAULT_FALLBACK_COUNTRY = "italy"
YEAR_PATTERN = re.compile(r"\b(19\d{2}|20\d{2}|2100)\b")
TIME_PATTERN = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
TIME_KEYWORDS = {
    "sunrise": time(6, 0),
    "morning": time(9, 0),
    "noon": time(12, 0),
    "afternoon": time(15, 0),
    "evening": time(18, 0),
    "sunset": time(19, 0),
    "night": time(21, 0),
}


@dataclass
class AgenticPlan:
    map_request: MapRequest
    metadata: dict[str, Any]
    notes: list[str]


###############################################################################
class AgenticMapPlanner:
    def __init__(self, fallback_country: str = DEFAULT_FALLBACK_COUNTRY) -> None:
        self.fallback_country = fallback_country if fallback_country in COUNTRY_PRESETS else DEFAULT_FALLBACK_COUNTRY

    ###########################################################################
    def build_plan(self, request: AgenticMapRequest) -> AgenticPlan:
        query = request.query.lower()
        notes: list[str] = []

        filter_name = self.detect_filter(query, notes)
        location_mode, location_payload = self.detect_location(query, notes)
        timeline_year = self.extract_year(query, notes)
        time_of_day = self.extract_time(query, notes)
        reference_date = self.compute_reference_date(timeline_year)

        temporal = TemporalContext(
            reference_date=reference_date,
            time_of_day=time_of_day,
            timeline_year=timeline_year,
        )

        if location_mode == "coordinates":
            map_request = MapRequest(
                filter=filter_name,
                mode="coordinates",
                coordinates=Coordinates(**location_payload),
                temporal=temporal,
            )
        else:
            map_request = MapRequest(
                filter=filter_name,
                mode="search",
                location=Location(**location_payload),
                temporal=temporal,
            )

        metadata: dict[str, Any] = {
            "filter": filter_name,
            "mode": map_request.mode,
            "location": location_payload,
            "timeline_year": temporal.timeline_year,
            "reference_date": temporal.reference_date.isoformat()
            if temporal.reference_date
            else None,
            "time_of_day": temporal.time_of_day.isoformat() if temporal.time_of_day else None,
        }

        return AgenticPlan(map_request=map_request, metadata=metadata, notes=notes)

    ###########################################################################
    def compose_status_message(
        self, request: AgenticMapRequest, base_message: str, notes: list[str]
    ) -> str:
        parts = [
            f"Agentic search executed with {request.agent_model} at temperature {request.temperature:.2f}.",
        ]
        if request.use_cloud_models and request.openai_model:
            parts.append(f"Cloud integration enabled via {request.openai_model}.")
        else:
            parts.append("Cloud integration disabled.")
        if notes:
            parts.append(" ".join(notes))
        if base_message:
            parts.append(base_message)
        return " ".join(segment.strip() for segment in parts if segment).strip()

    ###########################################################################
    def detect_filter(self, query: str, notes: list[str]) -> str:
        for layer_key, config in LAYER_CONFIGS.items():
            if config.filter_key.lower() in query:
                notes.append(f"Detected filter '{config.filter_key}'.")
                return config.filter_key
            if layer_key in query:
                notes.append(f"Matched filter '{config.filter_key}' from keyword '{layer_key}'.")
                return config.filter_key
        default_filter = LAYER_CONFIGS[DEFAULT_LAYER_KEY].filter_key
        notes.append(f"No filter specified; using default '{default_filter}'.")
        return default_filter

    ###########################################################################
    def detect_location(self, query: str, notes: list[str]) -> tuple[str, dict[str, Any]]:
        for city_key in CITY_PRESETS:
            if city_key in query:
                city_value = city_key.title()
                notes.append(f"Recognized city '{city_value}'.")
                return "search", {"city": city_value, "country": None}

        for country_key in COUNTRY_PRESETS:
            if country_key in query:
                country_value = country_key.title()
                notes.append(f"Recognized country '{country_value}'.")
                return "search", {"country": country_value, "city": None}

        fallback_country = self.fallback_country.title()
        notes.append(f"No explicit location found; defaulting to {fallback_country}.")
        return "search", {"country": fallback_country, "city": None}

    ###########################################################################
    def extract_year(self, query: str, notes: list[str]) -> int:
        match = YEAR_PATTERN.search(query)
        today_year = date.today().year
        if not match:
            notes.append(f"No year detected; using current year {today_year}.")
            return today_year

        year_value = int(match.group(0))
        if year_value < MIN_TIMELINE_YEAR:
            notes.append(
                f"Requested year {year_value} is before {MIN_TIMELINE_YEAR}; clamping to {MIN_TIMELINE_YEAR}."
            )
            return MIN_TIMELINE_YEAR
        if year_value > today_year:
            notes.append(
                f"Requested year {year_value} is in the future; clamping to {today_year}."
            )
            return today_year
        notes.append(f"Extracted timeline year {year_value} from query.")
        return year_value

    ###########################################################################
    def extract_time(self, query: str, notes: list[str]) -> time | None:
        time_match = TIME_PATTERN.search(query)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2))
            notes.append(f"Detected specific time {hour:02d}:{minute:02d}.")
            return time(hour=hour, minute=minute)

        for keyword, candidate_time in TIME_KEYWORDS.items():
            if keyword in query:
                notes.append(f"Interpreting '{keyword}' as {candidate_time.strftime('%H:%M')}.")
                return candidate_time
        return None

    ###########################################################################
    def compute_reference_date(self, year: int) -> date:
        today = date.today()
        safe_year = max(min(year, today.year), MIN_TIMELINE_YEAR)
        if safe_year == today.year:
            return today
        return date(safe_year, 6, 1)
