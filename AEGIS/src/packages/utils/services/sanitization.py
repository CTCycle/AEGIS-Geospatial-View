from __future__ import annotations

import re
import unicodedata

from AEGIS.src.packages.constants import COUNTRY_NAME_TO_ISO2, COUNTRY_SYNONYMS


###############################################################################
class LocationSanitizationService:
    COUNTRY_NAME_TO_ISO2 = COUNTRY_NAME_TO_ISO2

    def __init__(self) -> None:
        self.country_lookup = self.build_country_lookup()

    # -----------------------------------------------------------------------------
    def build_country_lookup(self) -> dict[str, str]:
        lookup: dict[str, str] = {}
        for name, code in self.COUNTRY_NAME_TO_ISO2.items():
            normalized = self.normalize_country_key(name)
            if normalized:
                lookup[normalized] = code
        for alias, target in COUNTRY_SYNONYMS.items():
            normalized_alias = self.normalize_country_key(alias)
            normalized_target = self.normalize_country_key(target)
            if normalized_alias and normalized_target and normalized_target in lookup:
                lookup.setdefault(normalized_alias, lookup[normalized_target])
        return lookup

    # -----------------------------------------------------------------------------
    def normalize_whitespace(self, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            return None
        return " ".join(stripped.split())

    # -----------------------------------------------------------------------------
    def normalize_country_key(self, value: str | None) -> str:
        if value is None:
            return ""
        normalized = unicodedata.normalize("NFKD", value)
        normalized = normalized.encode("ascii", "ignore").decode("ascii")
        normalized = normalized.lower()
        normalized = normalized.replace("&", "and")
        normalized = normalized.replace("'", " ")
        normalized = normalized.replace("’", " ")
        normalized = normalized.replace(".", " ")
        normalized = normalized.replace(",", " ")
        normalized = normalized.replace("-", " ")
        normalized = normalized.replace("saint", "st")
        normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        normalized = normalized.strip()
        if normalized.startswith("the "):
            normalized = normalized[4:]
        return normalized

    # -----------------------------------------------------------------------------
    def normalize_country(self, value: str | None) -> str | None:
        normalized = self.normalize_whitespace(value)
        if not normalized:
            return None
        if len(normalized) == 2 and normalized.isalpha():
            return normalized.upper()
        key = self.normalize_country_key(normalized)
        if not key:
            return None
        if key in self.country_lookup:
            return self.country_lookup[key]
        return None

    # -----------------------------------------------------------------------------
    def classify_query(self, value: str) -> str:
        if re.search(r"\d", value):
            return "address"
        return "place"

    # -----------------------------------------------------------------------------
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
