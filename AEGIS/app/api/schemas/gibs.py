from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, Field, FieldValidationInfo, field_validator


###############################################################################
class GIBSLayerConfiguration(BaseModel):
    filter_key: str = Field(..., min_length=1)
    layer_identifier: str = Field(..., min_length=1)
    tile_matrix_set: str = Field(..., min_length=1)
    image_format: str = Field(..., pattern=r"^[a-z0-9]+$")
    mime_type: str = Field(..., pattern=r"^[a-z]+/[a-z0-9+\-.]+$")
    projection: str = Field(default="epsg3857")
    min_zoom: int = Field(default=0, ge=0)
    max_zoom: int = Field(default=8, ge=0)
    default_zoom: int = Field(default=4, ge=0)

    @field_validator("projection", mode="before")
    @classmethod
    def normalize_projection(cls, value: str) -> str:
        cleaned = str(value).strip().lower()
        return cleaned or "epsg3857"

    @field_validator("image_format", mode="before")
    @classmethod
    def normalize_format(cls, value: str) -> str:
        cleaned = str(value).strip().lower()
        return cleaned or "jpg"

    @field_validator("mime_type", mode="before")
    @classmethod
    def normalize_mime(cls, value: str) -> str:
        cleaned = str(value).strip().lower()
        return cleaned or "image/jpeg"

    @field_validator("default_zoom")
    @classmethod
    def clamp_default_zoom(cls, value: int, info: FieldValidationInfo) -> int:
        minimum = int(info.data.get("min_zoom", 0))
        maximum = int(info.data.get("max_zoom", 8))
        if value < minimum:
            return minimum
        if value > maximum:
            return maximum
        return value


###############################################################################
class ResolvedLocation(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    source: Literal["coordinates", "city", "country"]
    reference: str | None = Field(default=None, max_length=200)


###############################################################################
class GIBSTileCoordinates(BaseModel):
    zoom: int = Field(..., ge=0)
    column: int = Field(..., ge=0)
    row: int = Field(..., ge=0)


###############################################################################
class GIBSRequest(BaseModel):
    service: Literal["wmts"] = "wmts"
    quality: Literal["best"] = "best"
    projection: str = Field(default="epsg3857")
    endpoint: str = Field(..., min_length=1)
    kvp_endpoint: str = Field(..., min_length=1)
    layer: str = Field(..., min_length=1)
    style: str = Field(default="default")
    time: str = Field(..., min_length=4)
    tile_matrix_set: str = Field(..., min_length=1)
    tile_matrix: int = Field(..., ge=0)
    tile_row: int = Field(..., ge=0)
    tile_col: int = Field(..., ge=0)
    image_format: str = Field(..., min_length=3)
    mime_type: str = Field(..., min_length=5)

    @property
    def restful_url(self) -> str:
        return (
            f"{self.endpoint}/{self.layer}/default/{self.time}/"
            f"{self.tile_matrix_set}/{self.tile_matrix}/{self.tile_row}/"
            f"{self.tile_col}.{self.image_format}"
        )

    @property
    def kvp_parameters(self) -> dict[str, str]:
        return {
            "SERVICE": "WMTS",
            "REQUEST": "GetTile",
            "VERSION": "1.0.0",
            "LAYER": self.layer,
            "STYLE": self.style,
            "TIME": self.time,
            "TILEMATRIXSET": self.tile_matrix_set,
            "TILEMATRIX": str(self.tile_matrix),
            "TILEROW": str(self.tile_row),
            "TILECOL": str(self.tile_col),
            "FORMAT": self.mime_type,
        }


###############################################################################
class GIBSImageryPayload(BaseModel):
    request: GIBSRequest
    layer: GIBSLayerConfiguration
    tile: GIBSTileCoordinates
    location: ResolvedLocation
    caption: str
    message: str
    image_url: str
    kvp_url: str


###############################################################################
class TemporalParameters(BaseModel):
    reference_date: date | None = None
    time_of_day: time | None = None
    fallback_year: int = Field(default=date.today().year, ge=1900)

    def iso_value(self) -> str:
        base_date = self.reference_date or date(self.fallback_year, 1, 1)
        if self.time_of_day is None:
            return base_date.isoformat()
        combined = datetime.combine(base_date, self.time_of_day)
        return combined.strftime("%Y-%m-%dT%H:%M:%SZ")

