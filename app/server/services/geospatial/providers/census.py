from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlencode

from server.common.typing import is_json_array, is_json_object, json_array, json_object

from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderInvalidQueryError,
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
class CensusProvider(GeospatialProvider):
    provider_id = "census"

    TIGERWEB_TRACTS_ROOT = (
        "https://tigerweb.geo.census.gov/arcgis/rest/services/"
        "TIGERweb/Tracts_Blocks/MapServer"
    )
    TIGERWEB_COUNTIES_ROOT = (
        "https://tigerweb.geo.census.gov/arcgis/rest/services/"
        "TIGERweb/State_County/MapServer"
    )
    TIGERWEB_HYDRO_URL = f"{TIGERWEB_TRACTS_ROOT.rsplit('/', 2)[0]}/Hydro/MapServer/0/query"
    ACS_API_ROOT = "https://api.census.gov/data"
    DEFAULT_ACS_VINTAGE = "2023"

    # -------------------------------------------------------------------------
    def __init__(self, *, fetcher: JsonFetcher | None = None) -> None:
        self.fetcher = fetcher or fetch_json_url

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        if "demographics" in request.capability_id or "acs" in request.capability_id:
            return await self._demographics(request)
        root = (
            self.TIGERWEB_HYDRO_URL
            if "hydrography" in request.capability_id
            else f"{self.TIGERWEB_TRACTS_ROOT}/0/query"
        )
        return await self._arcgis_layer(request, root, rendering_mode="geojson")

    # -------------------------------------------------------------------------
    async def _arcgis_layer(
        self,
        request: ProviderRequest,
        service_url: str,
        *,
        rendering_mode: str,
    ) -> ProviderResponse:
        query_url = _arcgis_query_url(service_url, request)
        if request.params.get("live"):
            payload = await call_json_fetcher(self.fetcher, query_url, None)
            features = _geojson_features(payload, provider_label="Census TIGERweb")
            return ProviderResponse(
                capability_id=request.capability_id,
                provider_id=self.provider_id,
                payload={
                    "renderingMode": rendering_mode,
                    "type": "FeatureCollection",
                    "features": features,
                    "totalResults": len(features),
                },
                attribution=["U.S. Census Bureau TIGERweb"],
                result_status="valid_empty" if not features else "ok",
                result_type="features",
            )
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": rendering_mode,
                "featuresUrl": query_url,
                "format": "geojson",
            },
            attribution=["U.S. Census Bureau TIGERweb"],
            result_type="metadata",
        )

    # -------------------------------------------------------------------------
    async def _demographics(self, request: ProviderRequest) -> ProviderResponse:
        geography = _geography_for_request(request)
        vintage = _acs_vintage(request)
        variable = str(request.params.get("variable") or "B01003_001E").strip().upper()
        if not re.fullmatch(r"B\d{5}_\d{3}[AE]", variable):
            raise ProviderInvalidQueryError("Census ACS variable must look like B01003_001E.")
        if not request.params.get("live"):
            return ProviderResponse(
                capability_id=request.capability_id,
                provider_id=self.provider_id,
                payload={
                    "renderingMode": "choropleth",
                    "status": "server-side-only",
                    "message": "Census boundary discovery and ACS joins are fetched by the server.",
                    "classificationField": "population",
                    "joinKey": "GEOID",
                    "vintage": vintage,
                    "marginOfErrorFields": [],
                },
                attribution=["U.S. Census Bureau TIGERweb", "U.S. Census Bureau ACS"],
                result_type="metadata",
            )

        boundary_layer_id, boundary_service_url = await self._discover_boundary_layer(
            geography=geography,
            vintage=vintage,
        )
        boundary_payload = await call_json_fetcher(
            self.fetcher,
            _arcgis_query_url(boundary_service_url, request),
            None,
        )
        features = _geojson_features(boundary_payload, provider_label="Census TIGERweb")
        acs_rows = await self._fetch_acs_rows(
            features,
            geography=geography,
            vintage=vintage,
            variable=variable,
        )
        joined: list[dict[str, Any]] = []
        join_count = 0
        for raw_feature in features:
            feature = dict(raw_feature)
            properties = dict(json_object(feature.get("properties")))
            geoid = _feature_geoid(feature)
            row = acs_rows.get(_normalize_geoid(geoid)) if geoid else None
            value = _float_or_none(row.get(variable)) if row else None
            if row is not None:
                join_count += 1
            properties["GEOID"] = geoid
            properties["population"] = _public_number(value)
            properties[variable] = _public_number(value)
            feature["properties"] = properties
            joined.append(feature)
        collection = {"type": "FeatureCollection", "features": joined}
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "choropleth",
                "type": "FeatureCollection",
                "features": joined,
                "featureCollection": collection,
                "totalResults": len(joined),
                "classificationField": "population",
                "joinKey": "GEOID",
                "vintage": vintage,
                "geography": geography,
                "variable": variable,
                "boundaryLayerId": boundary_layer_id,
                "joinCount": join_count,
                "marginOfErrorFields": [],
            },
            attribution=["U.S. Census Bureau TIGERweb", "U.S. Census Bureau ACS"],
            result_status="valid_empty" if not joined else "ok",
            result_type="features",
        )

    # -------------------------------------------------------------------------
    async def _discover_boundary_layer(
        self, *, geography: str, vintage: str
    ) -> tuple[str, str]:
        root = (
            self.TIGERWEB_COUNTIES_ROOT
            if geography == "county"
            else self.TIGERWEB_TRACTS_ROOT
        )
        root_payload = await self._fetch_json(f"{root}?f=json")
        candidates: list[tuple[int, int, str, str]] = []
        visited_groups: set[str] = set()

        async def collect(items: object, context: str, rank: int) -> None:
            if not is_json_array(items):
                return
            for raw_item in json_array(items):
                item = json_object(raw_item)
                layer_id = item.get("id")
                name = str(item.get("name") or "")
                if layer_id is None or not name:
                    continue
                item_context = f"{context} {name}".strip()
                lowered = item_context.casefold()
                geography_match = (
                    "county" in lowered
                    if geography == "county"
                    else "block group" in lowered
                    if geography == "block_group"
                    else "tract" in lowered and "block group" not in lowered
                )
                if geography_match:
                    exact_vintage = int(vintage in item_context) if vintage != "latest" else 0
                    year_match = max(
                        [int(value) for value in re.findall(r"\b20\d{2}\b", item_context)]
                        or [0]
                    )
                    candidates.append((exact_vintage, year_match, str(layer_id), item_context))
                child_layers = item.get("layers")
                await collect(child_layers, item_context, rank + 1)
                child_ids = json_array(item.get("subLayerIds"))
                if child_ids and str(layer_id) not in visited_groups:
                    visited_groups.add(str(layer_id))
                    child_payload = await self._fetch_json(f"{root}/{layer_id}?f=json")
                    await collect(child_payload.get("layers") if is_json_object(child_payload) else None, item_context, rank + 1)

        await collect(
            root_payload.get("layers") if is_json_object(root_payload) else None,
            "",
            0,
        )
        if not candidates:
            raise ProviderUnavailableError(
                f"Census TIGERweb has no {geography} boundary layer for the requested vintage."
            )
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        _, _, layer_id, _ = candidates[0]
        return layer_id, f"{root}/{layer_id}/query"

    # -------------------------------------------------------------------------
    async def _fetch_acs_rows(
        self,
        features: list[dict[str, Any]],
        *,
        geography: str,
        vintage: str,
        variable: str,
    ) -> dict[str, dict[str, str]]:
        states = sorted(
            {
                geoid[:2]
                for feature in features
                if (geoid := _normalize_geoid(_feature_geoid(feature)))
                and len(geoid) >= 2
            }
        )
        rows: dict[str, dict[str, str]] = {}
        for state in states:
            params: list[tuple[str, str]] = [
                ("get", f"NAME,{variable}"),
                ("for", f"{_acs_geography(geography)}:*"),
                ("in", f"state:{state}"),
            ]
            if geography in {"county", "tract", "block_group"}:
                params.append(("in", "county:*"))
            if geography in {"tract", "block_group"}:
                params.append(("in", "tract:*"))
            url = f"{self.ACS_API_ROOT}/{vintage}/acs/acs5?{urlencode(params)}"
            payload = await self._fetch_json(url)
            if not is_json_array(payload) or not payload or not is_json_array(payload[0]):
                raise ProviderMalformedPayloadError("Census ACS response must be a table.")
            headers = [str(value) for value in json_array(payload[0])]
            for raw_row in json_array(payload)[1:]:
                row_values = json_array(raw_row)
                if len(row_values) != len(headers):
                    raise ProviderMalformedPayloadError("Census ACS row width is invalid.")
                row = {headers[index]: str(value) for index, value in enumerate(row_values)}
                key = _acs_row_key(row, geography)
                if key:
                    rows[key] = row
        return rows

    # -------------------------------------------------------------------------
    async def _fetch_json(self, url: str) -> object:
        return await call_json_fetcher(self.fetcher, url, None)

###############################################################################
def _arcgis_query_url(service_url: str, request: ProviderRequest) -> str:
    params: dict[str, str] = {
        "f": "geojson",
        "outFields": "*",
        "where": "1=1",
        "returnGeometry": "true",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "outSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
    }
    if request.bbox is not None:
        min_lon, min_lat, max_lon, max_lat = request.bbox
        params["geometry"] = f"{min_lon},{min_lat},{max_lon},{max_lat}"
    return f"{service_url}?{urlencode(params)}"

###############################################################################
def _geojson_features(payload: object, *, provider_label: str) -> list[dict[str, Any]]:
    if not is_json_object(payload) or payload.get("type") != "FeatureCollection":
        raise ProviderMalformedPayloadError(f"{provider_label} response must be GeoJSON.")
    features = payload.get("features")
    if not is_json_array(features):
        raise ProviderMalformedPayloadError(f"{provider_label} response is missing features.")
    return [dict(json_object(item)) for item in json_array(features) if is_json_object(item)]

###############################################################################
def _geography_for_request(request: ProviderRequest) -> str:
    raw = str(
        request.params.get("geography")
        or ("county" if "acs_demographic_joins" in request.capability_id else "tract")
    ).strip().casefold().replace("-", "_")
    aliases = {"counties": "county", "tracts": "tract", "block_groups": "block_group"}
    geography = aliases.get(raw, raw)
    if geography not in {"county", "tract", "block_group"}:
        raise ProviderInvalidQueryError("Census geography must be county, tract, or block_group.")
    return geography

###############################################################################
def _acs_vintage(request: ProviderRequest) -> str:
    vintage = str(
        request.params.get("acs_vintage")
        or request.params.get("vintage")
        or CensusProvider.DEFAULT_ACS_VINTAGE
    ).strip()
    if vintage == "latest":
        vintage = CensusProvider.DEFAULT_ACS_VINTAGE
    if not re.fullmatch(r"20\d{2}", vintage):
        raise ProviderInvalidQueryError("Census ACS vintage must be a four-digit year.")
    return vintage

###############################################################################
def _acs_geography(geography: str) -> str:
    return {"county": "county", "tract": "tract", "block_group": "block group"}[geography]

###############################################################################
def _feature_geoid(feature: dict[str, Any]) -> str | None:
    properties = json_object(feature.get("properties"))
    for key, value in properties.items():
        if str(key).casefold() in {"geoid", "geo_id", "geoid10", "geoid20"}:
            return str(value)
    feature_id = feature.get("id")
    return str(feature_id) if feature_id is not None else None

###############################################################################
def _normalize_geoid(value: str | None) -> str:
    if not value:
        return ""
    text = str(value).strip()
    upper = text.upper()
    if "US" in upper:
        text = text[upper.index("US") + 2 :]
    return "".join(character for character in text if character.isdigit())

###############################################################################
def _acs_row_key(row: dict[str, str], geography: str) -> str:
    state = row.get("state", "").zfill(2)
    county = row.get("county", "").zfill(3)
    tract = row.get("tract", "").zfill(6)
    block_group = row.get("block group", "").zfill(1)
    if geography == "county":
        return state + county
    if geography == "tract":
        return state + county + tract
    return state + county + tract + block_group

###############################################################################
def _float_or_none(value: object) -> float | None:
    try:
        return None if value in {None, "", "-"} else float(value)
    except (TypeError, ValueError):
        return None

###############################################################################
def _public_number(value: float | None) -> int | float | None:
    if value is None:
        return None
    return int(value) if value.is_integer() else value
