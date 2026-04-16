from __future__ import annotations

from pydantic import BaseModel, Field

###############################################################################
class ExtractedLocation(BaseModel):
    address: str | None = None
    city: str | None = None
    country: str | None = None

###############################################################################
class ExtractedCoordinates(BaseModel):
    longitude: float | None = None
    latitude: float | None = None

###############################################################################
class ExtractedTimeReferences(BaseModel):
    year: int | None = None
    month: int | None = None
    day: int | None = None
    time_range: bool = False
    start_time: list[str] = Field(default_factory=list)
    end_time: list[str] = Field(default_factory=list)

###############################################################################
class ExtractedIntent(BaseModel):
    location: ExtractedLocation = Field(default_factory=ExtractedLocation)
    coordinates: ExtractedCoordinates = Field(default_factory=ExtractedCoordinates)
    location_type: str | None = None
    base_map_type: str | None = None
    time_references: ExtractedTimeReferences = Field(default_factory=ExtractedTimeReferences)
    user_goal: str = Field(default="", max_length=1000)
    filters: list[str] = Field(default_factory=list)
    area_of_interest: str | None = None
    certainty: float = Field(default=0.0, ge=0.0, le=1.0)

###############################################################################
class ExtractedIntentPatch(BaseModel):
    location: ExtractedLocation | None = None
    coordinates: ExtractedCoordinates | None = None
    location_type: str | None = None
    base_map_type: str | None = None
    time_references: ExtractedTimeReferences | None = None
    user_goal: str | None = Field(default=None, max_length=1000)
    filters: list[str] | None = None
    area_of_interest: str | None = None
    certainty: float | None = Field(default=None, ge=0.0, le=1.0)


###############################################################################
class StageAParserIntent(BaseModel):
    has_location: bool = False
    location_type: str | None = None
    has_time_reference: bool = False
    requires_search: bool = False
    requires_data: bool = False
    required_tools: list[str] = Field(default_factory=list)
    certainty: float = Field(default=0.0, ge=0.0, le=1.0)


###############################################################################
class StageBLocation(BaseModel):
    address: str | None = None
    city: str | None = None
    country: str | None = None
    location_type: str | None = None


###############################################################################
class StageBCoordinates(BaseModel):
    latitude: float | None = None
    longitude: float | None = None


###############################################################################
class StageBSearchExtraction(BaseModel):
    location: StageBLocation = Field(default_factory=StageBLocation)
    coordinates: StageBCoordinates = Field(default_factory=StageBCoordinates)
    time_reference: str | None = None
    base_map: str | None = None
    required_overlays: list[str] = Field(default_factory=list)
