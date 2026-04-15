from __future__ import annotations

from AEGIS.server.domain.extraction.models import (
    ExtractedCoordinates,
    ExtractedIntent,
    ExtractedIntentPatch,
    ExtractedLocation,
    ExtractedTimeReferences,
)

###############################################################################
def _merge_location(base: ExtractedLocation, patch: ExtractedLocation | None) -> ExtractedLocation:
    if patch is None:
        return base
    fields_set = getattr(patch, "model_fields_set", set())
    return ExtractedLocation(
        address=patch.address if "address" in fields_set else base.address,
        city=patch.city if "city" in fields_set else base.city,
        country=patch.country if "country" in fields_set else base.country,
    )

###############################################################################
def _merge_coordinates(
    base: ExtractedCoordinates, patch: ExtractedCoordinates | None
) -> ExtractedCoordinates:
    if patch is None:
        return base
    fields_set = getattr(patch, "model_fields_set", set())
    return ExtractedCoordinates(
        longitude=patch.longitude if "longitude" in fields_set else base.longitude,
        latitude=patch.latitude if "latitude" in fields_set else base.latitude,
    )

###############################################################################
def _merge_time(
    base: ExtractedTimeReferences, patch: ExtractedTimeReferences | None
) -> ExtractedTimeReferences:
    if patch is None:
        return base
    fields_set = getattr(patch, "model_fields_set", set())
    return ExtractedTimeReferences(
        year=patch.year if "year" in fields_set else base.year,
        month=patch.month if "month" in fields_set else base.month,
        day=patch.day if "day" in fields_set else base.day,
        time_range=patch.time_range if "time_range" in fields_set else base.time_range,
        start_time=list(patch.start_time) if "start_time" in fields_set else list(base.start_time),
        end_time=list(patch.end_time) if "end_time" in fields_set else list(base.end_time),
    )

###############################################################################
def merge_extracted_intent(base: ExtractedIntent, patch: ExtractedIntentPatch) -> ExtractedIntent:
    merged_coordinates = _merge_coordinates(base.coordinates, patch.coordinates)
    merged_location = _merge_location(base.location, patch.location)

    # When explicit coordinates are provided, preserve direct coordinate targeting.
    if merged_coordinates.latitude is not None and merged_coordinates.longitude is not None:
        merged_location = merged_location

    return ExtractedIntent(
        location=merged_location,
        coordinates=merged_coordinates,
        base_map_type=patch.base_map_type if "base_map_type" in patch.model_fields_set else base.base_map_type,
        time_references=_merge_time(base.time_references, patch.time_references),
        user_goal=patch.user_goal if "user_goal" in patch.model_fields_set else base.user_goal,
        filters=list(patch.filters) if "filters" in patch.model_fields_set else list(base.filters),
        area_of_interest=patch.area_of_interest if "area_of_interest" in patch.model_fields_set else base.area_of_interest,
        certainty=patch.certainty if "certainty" in patch.model_fields_set else base.certainty,
    )
