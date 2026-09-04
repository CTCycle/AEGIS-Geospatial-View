from __future__ import annotations

import math
from urllib.parse import quote, urlencode

from server.common.typing import is_json_array, is_json_object, json_object
from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderMalformedPayloadError,
    ProviderRequest,
    ProviderResponse,
    ProviderUnavailableError,
)
from server.services.geospatial.providers.http import (
    JsonFetcher,
    call_json_fetcher,
    fetch_json_url,
)


###############################################################################
class GBIFProvider(GeospatialProvider):
    provider_id = "gbif"
    OCCURRENCE_SEARCH_URL = "https://api.gbif.org/v1/occurrence/search"
    DEFAULT_INTERACTIVE_LIMIT = 300
    MAX_INTERACTIVE_LIMIT = 300

    # -------------------------------------------------------------------------
    def __init__(self, *, fetcher: JsonFetcher | None = None) -> None:
        self.fetcher = fetcher or fetch_json_url

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        if request.bbox is None:
            raise ProviderUnavailableError(
                "GBIF occurrence search requires a bounded geographic extent."
            )
        west, south, east, north = request.bbox
        if east < west:
            raise ProviderUnavailableError(
                "GBIF occurrence search does not support antimeridian-crossing extents."
            )

        limit = _bounded_int(
            request.params.get("limit"),
            default=self.DEFAULT_INTERACTIVE_LIMIT,
            maximum=self.MAX_INTERACTIVE_LIMIT,
        )
        params: dict[str, str | int] = {
            "geometry": _bbox_wkt(west=west, south=south, east=east, north=north),
            "hasCoordinate": "true",
            "limit": limit,
        }
        taxon_key = _optional_positive_int(request.params.get("taxonKey"))
        if taxon_key is not None:
            params["taxonKey"] = taxon_key
        year = _optional_text(request.params.get("year"))
        if year is not None:
            params["year"] = year
        basis_of_record = _optional_text(request.params.get("basisOfRecord"))
        if basis_of_record is not None:
            params["basisOfRecord"] = basis_of_record

        source_url = f"{self.OCCURRENCE_SEARCH_URL}?{urlencode(params)}"
        payload = await call_json_fetcher(self.fetcher, source_url)
        features = _normalize_occurrences(payload)
        total_matched = _non_negative_int(json_object(payload).get("count"))
        end_of_records = bool(json_object(payload).get("endOfRecords"))
        sampled = total_matched is not None and total_matched > len(features)
        warnings: list[str] = []
        warnings.append(
            "GBIF occurrence-search results require acknowledgement of contributing "
            "datasets and their licences; no single download DOI applies."
        )
        if sampled:
            warnings.append(
                f"GBIF matched {total_matched} records; this interactive result is limited to {limit}."
            )

        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "clustered-points",
                "features": features,
                "totalResults": len(features),
                "totalMatched": total_matched,
                "sampleLimit": limit,
                "sampled": sampled,
                "endOfRecords": end_of_records,
                "sourceUrl": source_url,
                "provenance": {
                    "citationRequired": True,
                    "citationGuidanceUrl": "https://www.gbif.org/citation-guidelines",
                    "downloadDoi": None,
                },
                "legend": {
                    "type": "category",
                    "label": "GBIF species occurrences",
                },
                "freshnessLabel": "GBIF indexed occurrence records",
            },
            attribution=["GBIF.org and contributing datasets"],
            warnings=warnings,
            result_status="valid_empty" if not features else "ok",
            result_type="features",
            source_url=source_url,
            coverage={
                "type": "bbox",
                "bbox": [west, south, east, north],
            },
        )


###############################################################################
def _normalize_occurrences(payload: object) -> list[dict[str, object]]:
    if not is_json_object(payload):
        raise ProviderMalformedPayloadError("GBIF payload must be a JSON object.")
    raw_results = payload.get("results")
    if not is_json_array(raw_results):
        raise ProviderMalformedPayloadError("GBIF payload is missing results.")

    features: list[dict[str, object]] = []
    for raw_result in raw_results:
        occurrence = json_object(raw_result)
        latitude = _finite_float(occurrence.get("decimalLatitude"))
        longitude = _finite_float(occurrence.get("decimalLongitude"))
        if latitude is None or longitude is None:
            continue
        if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
            continue
        gbif_id = str(occurrence.get("key") or occurrence.get("gbifID") or "").strip()
        scientific_name = _optional_text(occurrence.get("scientificName"))
        species = _optional_text(occurrence.get("species"))
        display_name = species or scientific_name or "GBIF occurrence"
        record_url = _gbif_url("occurrence", gbif_id)
        dataset_key = _optional_text(occurrence.get("datasetKey"))
        dataset_url = _gbif_url("dataset", dataset_key)
        features.append(
            {
                "id": gbif_id,
                "name": display_name,
                "category": "species_occurrence",
                "source": "gbif",
                "latitude": latitude,
                "longitude": longitude,
                "timestamp": occurrence.get("eventDate"),
                "url": record_url,
                "occurrenceUrl": record_url,
                "datasetUrl": dataset_url,
                "metadata": {
                    "scientificName": scientific_name,
                    "species": species,
                    "taxonKey": occurrence.get("taxonKey"),
                    "basisOfRecord": occurrence.get("basisOfRecord"),
                    "eventDate": occurrence.get("eventDate"),
                    "datasetKey": dataset_key,
                    "datasetTitle": occurrence.get("datasetTitle"),
                    "occurrenceUrl": record_url,
                    "datasetUrl": dataset_url,
                    "coordinateUncertaintyInMeters": occurrence.get(
                        "coordinateUncertaintyInMeters"
                    ),
                    "occurrenceStatus": occurrence.get("occurrenceStatus"),
                    "issues": occurrence.get("issues") or [],
                    "license": occurrence.get("license"),
                    "publishingOrgKey": occurrence.get("publishingOrgKey"),
                },
            }
        )
    return features


###############################################################################
def _bbox_wkt(*, west: float, south: float, east: float, north: float) -> str:
    return (
        "POLYGON(("
        f"{west} {south},{east} {south},{east} {north},{west} {north},{west} {south}"
        "))"
    )


###############################################################################
def _gbif_url(resource: str, identifier: object) -> str | None:
    value = _optional_text(identifier)
    return f"https://www.gbif.org/{resource}/{quote(value, safe='')}" if value else None


###############################################################################
def _finite_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


###############################################################################
def _bounded_int(value: object, *, default: int, maximum: int) -> int:
    parsed = _optional_positive_int(value)
    return min(parsed if parsed is not None else default, maximum)


###############################################################################
def _optional_positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


###############################################################################
def _non_negative_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


###############################################################################
def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
