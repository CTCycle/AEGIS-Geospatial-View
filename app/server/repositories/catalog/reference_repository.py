from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select

from server.domain.catalog import GeospatialLayerReferenceEntry
from server.repositories.database.contracts import DatabaseBackend
from server.repositories.schemas import (
    ReferenceCountryAliasRecord,
    ReferenceGeospatialLayerAliasRecord,
    ReferenceGeospatialLayerKeywordRecord,
    ReferenceGeospatialLayerRecord,
    ReferenceGibsLayerDefaultRecord,
    ReferenceGibsTileMatrixSetRecord,
)


class ReferenceCatalogRepository:
    def __init__(self, database: DatabaseBackend) -> None:
        self.database = database
        self._country_alias_to_iso2: dict[str, str] | None = None
        self._geospatial_layer_catalog: (
            tuple[GeospatialLayerReferenceEntry, ...] | None
        ) = None
        self._tile_matrix_resolution_map: dict[str, float] | None = None
        self._native_resolution_map: dict[str, float] | None = None
        self._date_fallback_days_map: dict[str, int] | None = None

    def load_country_alias_to_iso2(self) -> dict[str, str]:
        if self._country_alias_to_iso2 is not None:
            return dict(self._country_alias_to_iso2)
        with self.database.session() as session:
            rows = session.execute(select(ReferenceCountryAliasRecord)).scalars().all()
        self._country_alias_to_iso2 = {row.alias_key: row.iso2 for row in rows}
        return dict(self._country_alias_to_iso2)

    def load_geospatial_layer_catalog(
        self,
    ) -> tuple[GeospatialLayerReferenceEntry, ...]:
        if self._geospatial_layer_catalog is not None:
            return self._geospatial_layer_catalog
        with self.database.session() as session:
            layers = (
                session.execute(select(ReferenceGeospatialLayerRecord)).scalars().all()
            )
            aliases = (
                session.execute(select(ReferenceGeospatialLayerAliasRecord))
                .scalars()
                .all()
            )
            keywords = (
                session.execute(select(ReferenceGeospatialLayerKeywordRecord))
                .scalars()
                .all()
            )
        aliases_by_layer: dict[str, list[str]] = defaultdict(list)
        for row in aliases:
            aliases_by_layer[row.layer_id].append(row.alias)
        keywords_by_layer: dict[str, list[str]] = defaultdict(list)
        for row in keywords:
            keywords_by_layer[row.layer_id].append(row.keyword)
        self._geospatial_layer_catalog = tuple(
            GeospatialLayerReferenceEntry(
                layer_id=row.layer_id,
                display_name=row.display_name,
                group=row.group,
                provider=row.provider,
                aliases=tuple(aliases_by_layer.get(row.layer_id, [])),
                keywords=tuple(keywords_by_layer.get(row.layer_id, [])),
            )
            for row in layers
        )
        return self._geospatial_layer_catalog

    def load_gibs_tile_matrix_resolution_map(self) -> dict[str, float]:
        if self._tile_matrix_resolution_map is not None:
            return dict(self._tile_matrix_resolution_map)
        with self.database.session() as session:
            rows = (
                session.execute(select(ReferenceGibsTileMatrixSetRecord))
                .scalars()
                .all()
            )
        self._tile_matrix_resolution_map = {
            row.tile_matrix_set_id: row.meters_per_pixel for row in rows
        }
        return dict(self._tile_matrix_resolution_map)

    def load_gibs_layer_native_resolution_map(self) -> dict[str, float]:
        if self._native_resolution_map is not None:
            return dict(self._native_resolution_map)
        with self.database.session() as session:
            rows = (
                session.execute(select(ReferenceGibsLayerDefaultRecord)).scalars().all()
            )
        self._native_resolution_map = {
            row.layer_id: row.native_resolution_m
            for row in rows
            if row.native_resolution_m is not None
        }
        return dict(self._native_resolution_map)

    def load_gibs_layer_date_fallback_days_map(self) -> dict[str, int]:
        if self._date_fallback_days_map is not None:
            return dict(self._date_fallback_days_map)
        with self.database.session() as session:
            rows = (
                session.execute(select(ReferenceGibsLayerDefaultRecord)).scalars().all()
            )
        self._date_fallback_days_map = {
            row.layer_id: row.date_fallback_days
            for row in rows
            if row.date_fallback_days is not None
        }
        return dict(self._date_fallback_days_map)
