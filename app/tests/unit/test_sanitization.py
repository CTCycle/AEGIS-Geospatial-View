from __future__ import annotations

from server.repositories.catalog.reference_loader import load_reference_catalog
from server.services.sanitization import LocationSanitizationService


def test_country_canonical_names_and_aliases_normalize_through_reference_mapping() -> (
    None
):
    catalog = load_reference_catalog()
    alias_map = {
        entry.alias.strip().casefold(): entry.iso2 for entry in catalog.country_aliases
    }
    service = LocationSanitizationService(alias_map)

    assert service.normalize_country("United States") == "US"
    assert service.normalize_country("USA") == "US"
    assert service.normalize_country("Macau") == "MO"
