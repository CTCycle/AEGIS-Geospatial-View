from __future__ import annotations

from dataclasses import dataclass

from server.domain.catalog import ReferenceCatalog
from server.repositories.database.contracts import DatabaseBackend
from server.repositories.schemas import (
    ReferenceCountryAliasRecord,
    ReferenceCountryRecord,
    ReferenceGeospatialLayerAliasRecord,
    ReferenceGeospatialLayerKeywordRecord,
    ReferenceGeospatialLayerRecord,
    ReferenceGibsLayerDefaultRecord,
    ReferenceGibsTileMatrixSetRecord,
)


@dataclass(frozen=True)
class ReferenceSeedResult:
    countries_seeded: bool
    geospatial_layers_seeded: bool
    gibs_tile_matrix_sets_seeded: bool
    gibs_layer_defaults_seeded: bool


class ReferenceCatalogSeeder:
    def __init__(self, database: DatabaseBackend) -> None:
        self.database = database

    def seed_if_needed(self, catalog: ReferenceCatalog) -> ReferenceSeedResult:
        return ReferenceSeedResult(
            countries_seeded=self._seed_countries_if_empty(catalog),
            geospatial_layers_seeded=self._seed_geospatial_layers_if_empty(catalog),
            gibs_tile_matrix_sets_seeded=self._seed_gibs_tile_matrix_sets_if_empty(
                catalog
            ),
            gibs_layer_defaults_seeded=self._seed_gibs_layer_defaults_if_empty(catalog),
        )

    def _seed_countries_if_empty(self, catalog: ReferenceCatalog) -> bool:
        if self.database.count_records(ReferenceCountryRecord) > 0:
            return False
        with self.database.session() as session:
            session.add_all(
                ReferenceCountryRecord(iso2=item.iso2, name=item.name)
                for item in catalog.countries
            )
            session.add_all(
                ReferenceCountryAliasRecord(
                    alias_key=item.alias.strip().casefold(),
                    alias=item.alias,
                    iso2=item.iso2,
                )
                for item in catalog.country_aliases
            )
            session.commit()
        return True

    def _seed_geospatial_layers_if_empty(self, catalog: ReferenceCatalog) -> bool:
        if self.database.count_records(ReferenceGeospatialLayerRecord) > 0:
            return False
        with self.database.session() as session:
            session.add_all(
                ReferenceGeospatialLayerRecord(
                    layer_id=item.layer_id,
                    display_name=item.display_name,
                    group=item.group,
                    provider=item.provider,
                )
                for item in catalog.geospatial_layers
            )
            session.add_all(
                ReferenceGeospatialLayerAliasRecord(
                    alias_key=alias.strip().casefold(),
                    alias=alias,
                    layer_id=item.layer_id,
                )
                for item in catalog.geospatial_layers
                for alias in item.aliases
            )
            session.add_all(
                ReferenceGeospatialLayerKeywordRecord(
                    keyword_key=keyword.strip().casefold(),
                    keyword=keyword,
                    layer_id=item.layer_id,
                )
                for item in catalog.geospatial_layers
                for keyword in item.keywords
            )
            session.commit()
        return True

    def _seed_gibs_tile_matrix_sets_if_empty(self, catalog: ReferenceCatalog) -> bool:
        if self.database.count_records(ReferenceGibsTileMatrixSetRecord) > 0:
            return False
        with self.database.session() as session:
            session.add_all(
                ReferenceGibsTileMatrixSetRecord(
                    tile_matrix_set_id=item.tile_matrix_set_id,
                    meters_per_pixel=item.meters_per_pixel,
                )
                for item in catalog.gibs_tile_matrix_sets
            )
            session.commit()
        return True

    def _seed_gibs_layer_defaults_if_empty(self, catalog: ReferenceCatalog) -> bool:
        if self.database.count_records(ReferenceGibsLayerDefaultRecord) > 0:
            return False
        with self.database.session() as session:
            session.add_all(
                ReferenceGibsLayerDefaultRecord(
                    layer_id=item.layer_id,
                    native_resolution_m=item.native_resolution_m,
                    date_fallback_days=item.date_fallback_days,
                )
                for item in catalog.gibs_layer_defaults
            )
            session.commit()
        return True
