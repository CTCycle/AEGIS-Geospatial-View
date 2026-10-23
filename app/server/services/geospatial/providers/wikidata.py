from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from server.common.typing import is_json_array, is_json_object, json_object
from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderInvalidQueryError,
    ProviderMalformedPayloadError,
    ProviderRequest,
    ProviderResponse,
)
from server.services.geospatial.providers.http import (
    JsonFetcher,
    call_json_fetcher,
    fetch_json_url,
)

WIKIDATA_ENTITY_URL = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
WIKIDATA_PAGE_URL = "https://www.wikidata.org/wiki/{qid}"
USER_AGENT = "AEGIS-Geospatial-View/1.0 (place facts; keyless Wikidata entity data)"

# Wikidata properties and the unit entities their quantities may use.
POPULATION = "P1082"
AREA = "P2046"
ELEVATION = "P2044"
OFFICIAL_WEBSITE = "P856"
POINT_IN_TIME = "P585"
AREA_UNITS_KM2 = {"Q712226": 1.0, "Q35852": 0.01, "Q25343": 0.000001, "Q232291": 2.589988}
ELEVATION_UNITS_M = {"Q11573": 1.0, "Q3710": 0.3048}

###############################################################################
class WikidataProvider(GeospatialProvider):
    """Keyless place facts for a geocoded place's Wikidata entity."""

    provider_id = "wikidata"

    # -------------------------------------------------------------------------
    def __init__(self, *, fetcher: JsonFetcher | None = None) -> None:
        self.fetcher = fetcher or fetch_json_url

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        qid = str(request.params.get("wikidata_id") or "")
        source_url = WIKIDATA_PAGE_URL.format(qid=qid) if qid else None
        if not re.fullmatch(r"Q\d+", qid):
            # The geocoder links most cities, regions and countries; a
            # coordinate or an unlinked place simply has no entity to read.
            return ProviderResponse(
                capability_id=request.capability_id,
                provider_id=self.provider_id,
                payload={"kind": "place_facts", "facts": {}, "features": []},
                attribution=["Wikidata (CC0)"],
                result_status="valid_empty",
                result_type="metadata",
                warnings=["The resolved location has no linked Wikidata entity."],
                coverage={"type": "entity", "query_complete": True},
            )
        payload = await call_json_fetcher(
            self.fetcher,
            WIKIDATA_ENTITY_URL.format(qid=qid),
            {"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        entity = json_object(json_object(json_object(payload).get("entities")).get(qid))
        if not entity:
            raise ProviderMalformedPayloadError("Wikidata returned no entity for the identifier.")
        if entity.get("missing") is not None:
            raise ProviderInvalidQueryError("The Wikidata entity does not exist.")
        claims = json_object(entity.get("claims"))
        facts = place_facts(claims)
        facts["label"] = _english(entity.get("labels"))
        facts["description"] = _english(entity.get("descriptions"))
        facts["wikidata_id"] = qid
        latitude = request.params.get("latitude")
        longitude = request.params.get("longitude")
        feature = {
            "id": qid,
            "name": facts["label"],
            "category": "place_facts",
            "latitude": latitude,
            "longitude": longitude,
            **{key: value for key, value in facts.items() if not isinstance(value, dict)},
        }
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={"kind": "place_facts", "facts": facts, "features": [feature]},
            attribution=["Wikidata (CC0)"],
            fetched_at=datetime.now(UTC),
            result_status="ok",
            result_type="metadata",
            units={"population": "people", "area_km2": "km²", "elevation_m": "m"},
            source_url=source_url,
            coverage={
                "type": "entity",
                "entity": qid,
                "query_complete": True,
                # Facts describe the resolved place itself.
                "spatial_scope_satisfied": True,
                "temporal_scope_satisfied": True,
            },
        )

###############################################################################
def place_facts(claims: dict[str, Any]) -> dict[str, Any]:
    """Select the current value of each supported property with its date."""

    facts: dict[str, Any] = {}
    population = _best_statement(claims.get(POPULATION))
    if population is not None:
        amount = _quantity(population)
        if amount is not None:
            facts["population"] = int(round(amount))
            facts["population_point_in_time"] = _point_in_time(population)
    area = _best_statement(claims.get(AREA))
    if area is not None:
        value = _converted(area, AREA_UNITS_KM2)
        if value is not None:
            facts["area_km2"] = round(value, 3)
    elevation = _best_statement(claims.get(ELEVATION))
    if elevation is not None:
        value = _converted(elevation, ELEVATION_UNITS_M)
        if value is not None:
            facts["elevation_m"] = round(value, 1)
    website = _best_statement(claims.get(OFFICIAL_WEBSITE))
    if website is not None:
        url = json_object(json_object(website.get("mainsnak")).get("datavalue")).get("value")
        if isinstance(url, str) and url.startswith(("https://", "http://")):
            facts["official_website"] = url[:300]
    return facts

###############################################################################
def _best_statement(statements: Any) -> dict[str, Any] | None:
    """Preferred rank first, then the most recent point in time."""

    if not is_json_array(statements):
        return None
    candidates = [
        json_object(item)
        for item in statements
        if is_json_object(item)
        and item.get("rank") != "deprecated"
        and json_object(item.get("mainsnak")).get("snaktype") == "value"
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda item: (item.get("rank") == "preferred", _point_in_time(item) or ""),
    )

###############################################################################
def _quantity(statement: dict[str, Any]) -> float | None:
    value = json_object(json_object(json_object(statement.get("mainsnak")).get("datavalue")).get("value"))
    try:
        return float(str(value.get("amount")))
    except (TypeError, ValueError):
        return None

###############################################################################
def _converted(statement: dict[str, Any], factors: dict[str, float]) -> float | None:
    value = json_object(json_object(json_object(statement.get("mainsnak")).get("datavalue")).get("value"))
    unit = str(value.get("unit") or "").rsplit("/", 1)[-1]
    amount = _quantity(statement)
    if amount is None or unit not in factors:
        return None
    return amount * factors[unit]

###############################################################################
def _point_in_time(statement: dict[str, Any]) -> str | None:
    qualifiers = json_object(statement.get("qualifiers")).get(POINT_IN_TIME)
    if not is_json_array(qualifiers) or not qualifiers:
        return None
    value = json_object(json_object(json_object(qualifiers[0]).get("datavalue")).get("value"))
    time = str(value.get("time") or "")
    # Wikidata times look like "+2023-01-01T00:00:00Z".
    match = re.match(r"^\+?(\d{4}-\d{2}-\d{2})", time)
    return match.group(1) if match else None

###############################################################################
def _english(values: Any) -> str | None:
    value = json_object(json_object(values).get("en")).get("value")
    return value[:300] if isinstance(value, str) else None


__all__ = ["WikidataProvider", "place_facts"]
