from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from datetime import date, time

from pydantic import BaseModel, Field, field_validator, model_validator

from AEGIS.src.packages.configurations import APP_CONFIGURATIONS

GEOSPATIAL_SETTINGS = APP_CONFIGURATIONS.geospatial

type BBox = list[float]
type RangeComparator = Callable[[float, float], bool]


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
    timeline_year: int | None = Field(
        default=None, ge=GEOSPATIAL_SETTINGS.min_timeline_year
    )
    country: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=200)
    address: str | None = Field(default=None, max_length=400)
    use_coordinates: bool = Field(default=False)
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0)
    longitude: float | None = Field(default=None, ge=-180.0, le=180.0)
    filter: str | None = Field(default=None, max_length=200)
    geospatial_filter: str | None = Field(default=None, max_length=200)
    bbox: BBox | None = Field(default=None)
    radius_m: float = Field(default=2500.0, gt=0)
    image_width: int = Field(default=1024, ge=512, le=2048)
    image_height: int = Field(default=1024, ge=512, le=2048)
    image_crs: str = Field(default="EPSG:3857")
    image_format: str = Field(default="image/png")

    @field_validator(
        "country",
        "city",
        "address",
        "filter",
        "geospatial_filter",
        mode="before",
    )
    @classmethod
    def strip_location_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = str(value).strip()
        return stripped or None

    @field_validator("bbox", mode="before")
    @classmethod
    def normalize_bbox(cls, value: BBox | tuple[float, ...] | str | None) -> BBox | None:
        if value is None or value == "":
            return None
        if isinstance(value, str):
            parts = [part.strip() for part in value.split(",")]
            try:
                parsed = [float(part) for part in parts if part]
            except ValueError as exc:
                raise ValueError("BBox values must be numeric.") from exc
        elif isinstance(value, (list, tuple)):
            try:
                parsed = [float(part) for part in value]
            except (TypeError, ValueError) as exc:
                raise ValueError("BBox values must be numeric.") from exc
        else:
            raise ValueError("BBox must be a list, tuple, or comma separated string.")
        if len(parsed) != 4:
            raise ValueError("BBox must contain four values [minx,miny,maxx,maxy].")
        return parsed

    @field_validator("image_crs", mode="before")
    @classmethod
    def normalize_crs(cls, value: str) -> str:
        if not value:
            return "EPSG:3857"
        return str(value).upper()

    @field_validator("image_format", mode="before")
    @classmethod
    def normalize_format(cls, value: str) -> str:
        if not value:
            return "image/png"
        return str(value).lower()

    @model_validator(mode="after")
    def validate_location(self) -> "LocationSearchRequest":
        location = Location(
            country=self.country,
            city=self.city,
            address=self.address,
        )
        if self.use_coordinates:
            if self.latitude is None or self.longitude is None:
                raise ValueError(
                    "Provide both latitude and longitude when use_coordinates is enabled."
                )
        else:
            if not location.has_any_value():
                raise ValueError(
                    "Provide a country, city, or address when not using coordinates."
                )
        if not (self.reference_date or self.datetime):
            raise ValueError(
                "Provide reference_date or datetime to determine imagery date."
            )
        if self.bbox is None and self.use_coordinates:
            if self.latitude is None or self.longitude is None:
                raise ValueError(
                    "Provide either bbox or coordinates for satellite imagery."
                )
        if self.bbox:
            minx, miny, maxx, maxy = self.bbox
            comparator: RangeComparator = lambda lower, upper: lower < upper
            if not comparator(minx, maxx) or not comparator(miny, maxy):
                raise ValueError("BBox min values must be smaller than max values.")
                if self.image_crs == "EPSG:3857":
                    for value in (minx, maxx, miny, maxy):
                        if abs(value) > GEOSPATIAL_SETTINGS.max_mercator_extent:
                            raise ValueError(
                                "BBox exceeds EPSG:3857 valid extent +/-20037508.3427892."
                            )
                elif self.image_crs == "EPSG:4326":
                    if (
                        miny < GEOSPATIAL_SETTINGS.min_lat
                        or maxy > GEOSPATIAL_SETTINGS.max_lat
                    ):
                        raise ValueError("Latitude values must be within [-90, 90].")
                    if (
                        minx < GEOSPATIAL_SETTINGS.min_lon
                        or maxx > GEOSPATIAL_SETTINGS.max_lon
                    ):
                        raise ValueError("Longitude values must be within [-180, 180].")
        return self
