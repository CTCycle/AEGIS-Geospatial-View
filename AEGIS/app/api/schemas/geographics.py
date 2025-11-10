from __future__ import annotations

import datetime as dt
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
    address: str | None = Field(default=None, max_length=400)

    @field_validator("country", "city", "address", mode="before")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = str(value).strip()
        return stripped or None

    def has_any_value(self) -> bool:
        return bool(self.country or self.city or self.address)


###############################################################################
class LocationSearchRequest(BaseModel):
    datetime: dt.datetime | None = Field(default=None)
    reference_date: date | None = Field(default=None)
    time_of_day: time | None = Field(default=None)
    timeline_year: int | None = Field(default=None, ge=MIN_TIMELINE_YEAR)
    country: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=200)
    address: str | None = Field(default=None, max_length=400)
    use_coordinates: bool = Field(default=False)
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0)
    longitude: float | None = Field(default=None, ge=-180.0, le=180.0)
    filter: str | None = Field(default=None, max_length=200)
    satellite_style: str | None = Field(default=None, max_length=200)
    geospatial_filter: str | None = Field(default=None, max_length=200)

    @field_validator(
        "country",
        "city",
        "address",
        "filter",
        "satellite_style",
        "geospatial_filter",
        mode="before",
    )
    @classmethod
    def strip_location_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = str(value).strip()
        return stripped or None

    @model_validator(mode="after")
    def validate_location(self) -> "LocationSearchRequest":
        if self.use_coordinates:
            if self.latitude is None or self.longitude is None:
                raise ValueError(
                    "Provide both latitude and longitude when use_coordinates is enabled."
                )
        else:
            if not self.address:
                raise ValueError("Provide an address when not using coordinates.")
        return self

    def as_query_payload(self) -> dict[str, object]:
        payload = self.model_dump(exclude_none=True)
        payload["mode"] = "coordinates" if self.use_coordinates else "search"
        return payload
