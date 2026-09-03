# GBIF Biodiversity Provider

Last updated: 2026-09-03

## Purpose

AEGIS uses the Global Biodiversity Information Facility occurrence-search API for bounded, interactive biodiversity exploration.

The core capability is `gbif_species_occurrences`.

## Access

Normal GBIF occurrence search is public and does not require authentication. AEGIS does not use authenticated asynchronous GBIF bulk downloads for this capability.

The provider deliberately keeps requests bounded by the selected map extent and caps interactive pages at the GBIF search maximum of 300 records, with an AEGIS default of 100.

## Semantics

Returned records are species occurrences, observations, specimens, or other GBIF basis-of-record categories. They are not a complete inventory of species in the selected area and must not be used to infer species absence.

AEGIS preserves provenance and quality metadata where supplied, including:

- `basisOfRecord`
- `eventDate`
- `datasetKey`
- `coordinateUncertaintyInMeters`
- `issues`
- per-record `license`

If GBIF reports more matching records than the current interactive page contains, the normalized response is explicitly marked as sampled and reports the total matched count.

## Query Parameters

Supported optional provider parameters are:

- `limit`, clamped to 1 through 300
- `taxonKey`
- `year`
- `basisOfRecord`

The capability requires a non-antimeridian-crossing bounding box. Large or exhaustive exports should use GBIF's authenticated download workflow outside the core AEGIS interactive path.

## Sources

- GBIF occurrence API: https://techdocs.gbif.org/en/openapi/v1/occurrence
- GBIF API reference: https://techdocs.gbif.org/en/openapi/
