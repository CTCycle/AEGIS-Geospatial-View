from __future__ import annotations

from datetime import date, time

from pydantic import BaseModel, Field, field_validator, model_validator

MIN_TIMELINE_YEAR = 1900


###############################################################################
class Coordinates(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)


###############################################################################
class Location(BaseModel):
    country: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=200)

    @field_validator("country", "city", mode="before")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = str(value).strip()
        return stripped or None

    def has_any_value(self) -> bool:
        return bool(self.country or self.city)


###############################################################################
class TemporalContext(BaseModel):
    reference_date: date | None = None
    time_of_day: time | None = None
    timeline_year: int = Field(..., ge=MIN_TIMELINE_YEAR)

    @model_validator(mode="after")
    def ensure_year_bounds(self) -> "TemporalContext":
        if self.reference_date is not None and self.timeline_year > date.today().year:
            self.timeline_year = date.today().year
        if self.timeline_year < MIN_TIMELINE_YEAR:
            self.timeline_year = MIN_TIMELINE_YEAR
        return self


###############################################################################
class MapRequest(BaseModel):
    filter: str | None = Field(default=None, max_length=200)
    mode: str = Field(default="search")
    coordinates: Coordinates | None = None
    location: Location | None = None
    temporal: TemporalContext

    @field_validator("filter", mode="before")
    @classmethod
    def strip_filter(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = str(value).strip()
        return stripped or None

    @field_validator("mode", mode="before")
    @classmethod
    def normalize_mode(cls, value: str) -> str:
        if not value:
            return "search"
        lowered = str(value).strip().lower()
        if lowered not in {"search", "coordinates"}:
            return "search"
        return lowered

    @model_validator(mode="after")
    def validate_sources(self) -> "MapRequest":
        if self.mode == "coordinates":
            if self.coordinates is None:
                raise ValueError("Coordinates are required when coordinate mode is selected.")
        else:
            if self.location is None or not self.location.has_any_value():
                raise ValueError("Provide at least a city or country when search mode is selected.")
        return self

