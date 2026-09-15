"""Provider-neutral location signals used by the native location tool."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


LocationSignalType = Literal[
    "address",
    "airport",
    "city",
    "country",
    "coordinates",
    "deictic",
    "poi",
    "feature",
    "landmark",
    "region",
    "river",
    "road",
    "street",
    "station",
    "neighborhood",
    "district",
    "municipality",
    "county",
    "province",
    "state",
]


class LocationSignal(BaseModel):
    """One bounded location signal passed to the resolver."""

    model_config = ConfigDict(extra="forbid")

    signal_type: LocationSignalType
    raw_value: str
    normalized_value: str | None = None
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0)
    longitude: float | None = Field(default=None, ge=-180.0, le=180.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source: Literal["text", "memory", "model"] = "text"


__all__ = ["LocationSignal", "LocationSignalType"]
