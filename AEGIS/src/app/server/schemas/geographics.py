from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from datetime import time
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from AEGIS.src.packages.configurations import configurations

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

    # -------------------------------------------------------------------------
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
    time_of_day: time | None = Field(default=None)
    timeline_year: int | None = Field(
        default=None, ge=configurations.geospatial.min_timeline_year
    )
    country: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=200)
    address: str | None = Field(default=None, max_length=400)
    use_coordinates: bool = Field(default=False)
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0)
    longitude: float | None = Field(default=None, ge=-180.0, le=180.0)
    filters: list[str] = Field(default_factory=list)
    geospatial_filter: str | None = Field(default=None, max_length=200)
    bbox: BBox | None = Field(default=None)
    radius_m: float = Field(default=2500.0, gt=0)
    map_size_m: float = Field(default=configurations.maps.default_size_m, gt=0)
    map_tiles: str | None = Field(default=configurations.maps.tiles, max_length=200)
    image_width: int = Field(default=configurations.gibs.image_width, ge=512, le=2048)
    image_height: int = Field(default=configurations.gibs.image_height, ge=512, le=2048)
    image_crs: str = Field(default="EPSG:3857")
    image_format: str = Field(default="image/png")

    @field_validator(
        "country",
        "city",
        "address",
        "geospatial_filter",
        "map_tiles",
        mode="before",
    )
    # -------------------------------------------------------------------------
    @classmethod
    def strip_location_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = str(value).strip()
        return stripped or None

    # -------------------------------------------------------------------------
    @field_validator("filters", mode="before")
    @classmethod
    def normalize_filters(
        cls, value: list[str] | tuple[str, ...] | str | None
    ) -> list[str]:
        if value is None:
            return []
        candidates: list[str] = []
        values = [value] if isinstance(value, str) else list(value)
        for candidate in values:
            normalized = cls.strip_location_text(candidate)
            if normalized is None:
                continue
            if normalized.lower() == "none":
                continue
            if normalized in candidates:
                continue
            candidates.append(normalized)
        return candidates

    # -------------------------------------------------------------------------
    @field_validator("bbox", mode="before")
    @classmethod
    def normalize_bbox(
        cls, value: BBox | tuple[float, ...] | str | None
    ) -> BBox | None:
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

    # -------------------------------------------------------------------------
    @field_validator("image_crs", mode="before")
    @classmethod
    def normalize_crs(cls, value: str) -> str:
        if not value:
            return "EPSG:3857"
        return str(value).upper()

    # -------------------------------------------------------------------------
    @field_validator("image_format", mode="before")
    @classmethod
    def normalize_format(cls, value: str) -> str:
        if not value:
            return "image/png"
        return str(value).lower()

    # -------------------------------------------------------------------------
    @field_validator("map_tiles", mode="before")
    @classmethod
    def normalize_map_tiles(cls, value: str | None) -> str:
        if value is None:
            return configurations.maps.tiles
        normalized = str(value).strip()
        return normalized or configurations.maps.tiles

    # -------------------------------------------------------------------------
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
        if not self.datetime:
            raise ValueError("Provide datetime to determine imagery date.")
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
                    if abs(value) > configurations.geospatial.max_mercator_extent:
                        raise ValueError(
                            "BBox exceeds EPSG:3857 valid extent +/-20037508.3427892."
                        )
            elif self.image_crs == "EPSG:4326":
                if (
                    miny < configurations.geospatial.min_lat
                    or maxy > configurations.geospatial.max_lat
                ):
                    raise ValueError("Latitude values must be within [-90, 90].")
                if (
                    minx < configurations.geospatial.min_lon
                    or maxx > configurations.geospatial.max_lon
                ):
                    raise ValueError("Longitude values must be within [-180, 180].")
        return self


###############################################################################
class MapLayerUpdateRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    layers: list[str] | None = Field(default=None)
    add_layers: list[str] = Field(default_factory=list)
    remove_layers: list[str] = Field(default_factory=list)

    # -------------------------------------------------------------------------
    @field_validator("payload")
    @classmethod
    def validate_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict) or not value:
            raise ValueError("payload must be a non-empty object.")
        return value
