from __future__ import annotations

import re
from collections.abc import Mapping

from server.repositories.catalog.reference_repository import ReferenceCatalogRepository
from server.repositories.database.contracts import DatabaseBackend

###############################################################################
class LocationSanitizationService:

    # -------------------------------------------------------------------------
    def __init__(self, country_alias_to_iso2: Mapping[str, str]) -> None:
        self._country_alias_to_iso2 = dict(country_alias_to_iso2)

    # -------------------------------------------------------------------------
    def normalize_whitespace(self, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            return None
        return " ".join(stripped.split())

    # -------------------------------------------------------------------------
    def normalize_country_key(self, value: str | None) -> str:
        if value is None:
            return ""
        return " ".join(value.strip().casefold().split())

    # -------------------------------------------------------------------------
    def normalize_country(self, value: str | None) -> str | None:
        normalized = self.normalize_whitespace(value)
        if not normalized:
            return None
        if len(normalized) == 2 and normalized.isalpha():
            return normalized.upper()
        key = self.normalize_country_key(normalized)
        if not key:
            return None
        if key in self._country_alias_to_iso2:
            return self._country_alias_to_iso2[key]
        return None

    # -------------------------------------------------------------------------
    def classify_query(self, value: str) -> str:
        if re.search(r"\d", value):
            return "address"
        return "place"

    # -------------------------------------------------------------------------
    def sanitize_location_inputs(
        self,
        address: str,
        city: str | None,
        country: str | None,
    ) -> dict[str, str | None]:
        sanitized_address = self.normalize_whitespace(address) or ""
        sanitized_city = self.normalize_whitespace(city)
        sanitized_country = self.normalize_whitespace(country)
        country_code = self.normalize_country(country)
        classification = self.classify_query(sanitized_address)
        query_components: list[str] = [sanitized_address]
        if sanitized_city and sanitized_city.lower() not in sanitized_address.lower():
            query_components.append(sanitized_city)
        if not country_code and sanitized_country:
            query_components.append(sanitized_country)
        query = ", ".join(component for component in query_components if component)
        return {
            "address": sanitized_address,
            "city": sanitized_city,
            "country_code": country_code,
            "country": sanitized_country,
            "classification": classification,
            "query": query,
        }


###############################################################################
def build_location_sanitization_service(
    database: DatabaseBackend,
) -> LocationSanitizationService:
    repository = ReferenceCatalogRepository(database)
    return LocationSanitizationService(repository.load_country_alias_to_iso2())
