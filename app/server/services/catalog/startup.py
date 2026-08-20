from __future__ import annotations

from server.repositories.catalog.reference_seeder import ReferenceCatalogSeeder
from server.repositories.database.contracts import DatabaseBackend
from server.services.catalog.loader import load_reference_catalog

###############################################################################
def seed_reference_catalog(database: DatabaseBackend) -> None:
    """Load static catalog files and seed their relational reference tables."""
    ReferenceCatalogSeeder(database).seed_if_needed(load_reference_catalog())
