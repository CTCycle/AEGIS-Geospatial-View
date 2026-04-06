from __future__ import annotations

from AEGIS.server.domain.extraction.models import (
    ExtractedCoordinates,
    ExtractedIntent,
    ExtractedIntentPatch,
    ExtractedLocation,
    ExtractedTimeReferences,
)


def _merge_location(base: ExtractedLocation, patch: ExtractedLocation | None) -> ExtractedLocation:
    if patch is None:
        return base
    return ExtractedLocation(
        address=patch.address if patch.address is not None else base.address,
        city=patch.city if patch.city is not None else base.city,
        country=patch.country if patch.country is not None else base.country,
    )


def _merge_coordinates(
    base: ExtractedCoordinates, patch: ExtractedCoordinates | None
) -> ExtractedCoordinates:
    if patch is None:
        return base
    return ExtractedCoordinates(
        longitude=patch.longitude if patch.longitude is not None else base.longitude,
        latitude=patch.latitude if patch.latitude is not None else base.latitude,
    )


def _merge_time(
    base: ExtractedTimeReferences, patch: ExtractedTimeReferences | None
) -> ExtractedTimeReferences:
    if patch is None:
        return base
    return ExtractedTimeReferences(
        year=patch.year if patch.year is not None else base.year,
        month=patch.month if patch.month is not None else base.month,
        day=patch.day if patch.day is not None else base.day,
        time_range=patch.time_range if patch.time_range is not None else base.time_range,
        start_time=list(patch.start_time) if patch.start_time else list(base.start_time),
        end_time=list(patch.end_time) if patch.end_time else list(base.end_time),
    )


def merge_extracted_intent(base: ExtractedIntent, patch: ExtractedIntentPatch) -> ExtractedIntent:
    merged_coordinates = _merge_coordinates(base.coordinates, patch.coordinates)
    merged_location = _merge_location(base.location, patch.location)

    # When explicit coordinates are provided, preserve direct coordinate targeting.
    if merged_coordinates.latitude is not None and merged_coordinates.longitude is not None:
        merged_location = merged_location

    return ExtractedIntent(
        location=merged_location,
        coordinates=merged_coordinates,
        base_map_type=patch.base_map_type if patch.base_map_type is not None else base.base_map_type,
        time_references=_merge_time(base.time_references, patch.time_references),
        user_goal=patch.user_goal if patch.user_goal is not None else base.user_goal,
        filters=list(patch.filters) if patch.filters else list(base.filters),
        area_of_interest=patch.area_of_interest if patch.area_of_interest is not None else base.area_of_interest,
        certainty=patch.certainty if patch.certainty is not None else base.certainty,
    )
