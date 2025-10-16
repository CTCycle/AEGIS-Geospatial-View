from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


###############################################################################
class GIBSMatrixSet(BaseModel):
    identifier: str = Field(..., min_length=1)
    projection: str = Field(..., min_length=4)
    tile_width: int = Field(..., gt=0)
    tile_height: int = Field(..., gt=0)
    top_left_corner: tuple[float, float]
    scale_denominators: list[float]
    matrix_widths: list[int]
    matrix_heights: list[int]
    levels: list[str]

    @field_validator("projection", mode="before")
    @classmethod
    def normalize_projection(cls, value: str) -> str:
        return str(value).strip().lower()


###############################################################################
class GIBSTimeDomain(BaseModel):
    default: str | None = None
    current: bool = False
    values: list[str] = Field(default_factory=list)
    limited: bool = False

    def sorted_values(self) -> list[str]:
        return sorted(set(self.values))


###############################################################################
class WMTSProjectionCapabilities(BaseModel):
    matrix_sets: list[str] = Field(default_factory=list)
    formats: list[str] = Field(default_factory=list)
    styles: list[str] = Field(default_factory=list)
    time_domains: dict[str, GIBSTimeDomain] = Field(default_factory=dict)


###############################################################################
class WMSProjectionCapabilities(BaseModel):
    versions: list[str] = Field(default_factory=list)
    formats: list[str] = Field(default_factory=list)
    styles: list[str] = Field(default_factory=list)
    time_domain: GIBSTimeDomain | None = None
    nearest_value: bool = False


###############################################################################
class GIBSLayerProjection(BaseModel):
    projection: str = Field(..., min_length=4)
    styles: list[str] = Field(default_factory=list)
    formats: list[str] = Field(default_factory=list)
    time_supported: bool = False
    wmts: WMTSProjectionCapabilities | None = None
    wms: dict[str, WMSProjectionCapabilities] = Field(default_factory=dict)

    @field_validator("projection", mode="before")
    @classmethod
    def normalize_projection(cls, value: str) -> str:
        return str(value).strip().lower()


###############################################################################
class GIBSLayer(BaseModel):
    identifier: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    projections: dict[str, GIBSLayerProjection] = Field(default_factory=dict)


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
    tile_matrix: str = Field(..., min_length=1)
    tile_matrix_set: str = Field(..., min_length=1)


###############################################################################
class WMSBoundingBox(BaseModel):
    minx: float
    miny: float
    maxx: float
    maxy: float
    axis_order: Literal["lonlat", "latlon"] = "lonlat"

    def as_list(self) -> list[str]:
        if self.axis_order == "lonlat":
            return [
                f"{self.minx:.8f}",
                f"{self.miny:.8f}",
                f"{self.maxx:.8f}",
                f"{self.maxy:.8f}",
            ]
        return [
            f"{self.miny:.8f}",
            f"{self.minx:.8f}",
            f"{self.maxy:.8f}",
            f"{self.maxx:.8f}",
        ]


###############################################################################
class GIBSRequest(BaseModel):
    service: Literal["wmts", "wms"]
    quality: Literal["best", "std", "nrt", "all"] = "best"
    projection: str = Field(..., min_length=4)
    endpoint: str = Field(..., min_length=1)
    kvp_endpoint: str = Field(..., min_length=1)
    layer: str = Field(..., min_length=1)
    style: str = Field(default="default", min_length=0)
    time: str = Field(..., min_length=4)
    tile_matrix_set: str | None = None
    tile_matrix: str | None = None
    tile_row: int | None = None
    tile_col: int | None = None
    image_format: str = Field(..., min_length=3)
    mime_type: str = Field(..., min_length=5)
    width: int | None = None
    height: int | None = None
    bbox: WMSBoundingBox | None = None
    wms_version: Literal["1.1.1", "1.3.0"] | None = None
    axis_order: Literal["lonlat", "latlon"] = "lonlat"
    nearest_value: bool | None = None

    @field_validator("projection", mode="before")
    @classmethod
    def normalize_projection(cls, value: str) -> str:
        return str(value).strip().lower()

    @property
    def restful_url(self) -> str:
        if self.service == "wmts":
            if not all(
                [
                    self.tile_matrix_set,
                    self.tile_matrix,
                    self.tile_row is not None,
                    self.tile_col is not None,
                ]
            ):
                raise ValueError("Incomplete WMTS tile parameters for RESTful access.")
            return (
                f"{self.endpoint}/{self.layer}/default/{self.time}/"
                f"{self.tile_matrix_set}/{self.tile_matrix}/{self.tile_row}/"
                f"{self.tile_col}.{self.image_format}"
            )
        parameters = self.kvp_parameters
        query = "&".join(f"{key}={value}" for key, value in parameters.items())
        return f"{self.kvp_endpoint}?{query}"

    @property
    def kvp_parameters(self) -> dict[str, str]:
        if self.service == "wmts":
            if not all(
                [
                    self.tile_matrix_set,
                    self.tile_matrix,
                    self.tile_row is not None,
                    self.tile_col is not None,
                ]
            ):
                raise ValueError("Incomplete WMTS tile parameters for KVP access.")
            return {
                "SERVICE": "WMTS",
                "REQUEST": "GetTile",
                "VERSION": "1.0.0",
                "LAYER": self.layer,
                "STYLE": self.style,
                "TIME": self.time,
                "TILEMATRIXSET": self.tile_matrix_set,
                "TILEMATRIX": self.tile_matrix,
                "TILEROW": str(self.tile_row),
                "TILECOL": str(self.tile_col),
                "FORMAT": self.mime_type,
            }
        if self.bbox is None:
            raise ValueError("WMS requests require a bounding box.")
        bbox_values = ",".join(self.bbox.as_list())
        parameters: dict[str, str] = {
            "SERVICE": "WMS",
            "REQUEST": "GetMap",
            "LAYERS": self.layer,
            "STYLES": self.style,
            "FORMAT": self.mime_type,
            "TIME": self.time,
            "WIDTH": str(self.width or 1024),
            "HEIGHT": str(self.height or 1024),
            "BBOX": bbox_values,
        }
        version = self.wms_version or "1.1.1"
        parameters["VERSION"] = version
        if version == "1.3.0":
            parameters["CRS"] = self.projection.upper().replace("epsg", "EPSG:")
        else:
            parameters["SRS"] = self.projection.upper().replace("epsg", "EPSG:")
        if self.nearest_value is not None:
            parameters["nearestValue"] = "1" if self.nearest_value else "0"
        return parameters


###############################################################################
class GIBSImageryPayload(BaseModel):
    request: GIBSRequest
    layer: GIBSLayer
    projection: str
    tile: GIBSTileCoordinates | None = None
    bbox: WMSBoundingBox | None = None
    location: ResolvedLocation
    caption: str
    message: str
    image_url: str
    kvp_url: str
    debug: dict[str, Any] = Field(default_factory=dict)


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


###############################################################################
class TemporalSelection(BaseModel):
    iso_value: str
    snapped: bool = False
    reason: str | None = None


###############################################################################
class WMTSRequestOptions(BaseModel):
    tile_matrix_set: str | None = None
    tile_matrix: str | None = None
    zoom: int | None = None


###############################################################################
class WMSRequestOptions(BaseModel):
    version: Literal["1.1.1", "1.3.0"] = "1.1.1"
    format: str | None = None
    style: str | None = None
    width: int = Field(default=1024, ge=64, le=8192)
    height: int = Field(default=1024, ge=64, le=8192)
    size_km: float | None = Field(default=200.0, gt=0.0)
    width_km: float | None = Field(default=None, gt=0.0)
    height_km: float | None = Field(default=None, gt=0.0)

    @field_validator("format", "style", mode="before")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @model_validator(mode="after")
    def ensure_extent(self) -> "WMSRequestOptions":
        if self.size_km is None and (self.width_km is None or self.height_km is None):
            raise ValueError(
                "Specify either a uniform size_km or both width_km and height_km for WMS AOI."
            )
        if self.size_km is not None and (
            self.width_km is not None or self.height_km is not None
        ):
            raise ValueError(
                "Provide either size_km or width_km/height_km, not a combination of both."
            )
        return self


###############################################################################
class GIBSMapOptions(BaseModel):
    service: Literal["wmts", "wms"] = "wmts"
    projection: Literal["epsg4326", "epsg3857", "epsg3413", "epsg3031"] = "epsg3857"
    endpoint_flavor: Literal["best", "std", "nrt", "all"] = "best"
    layer_id: str | None = Field(default=None, min_length=1)
    style: str | None = Field(default=None, min_length=0)
    format: str | None = Field(default=None, min_length=0)
    wmts: WMTSRequestOptions | None = None
    wms: WMSRequestOptions | None = None
    time_value: str | None = None

    @field_validator("layer_id", "style", "format", mode="before")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None


