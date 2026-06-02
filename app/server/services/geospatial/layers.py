from __future__ import annotations

from collections.abc import Callable
from typing import Any
from typing import TYPE_CHECKING

from server.domain.catalog import GeospatialLayerReferenceEntry
from server.domain.layers import LayerProviderEntry
from server.services.catalog.reference_repository import ReferenceCatalogRepository

if TYPE_CHECKING:
    from server.repositories.database.backend import DatabaseBackend

type LayerDefinition = dict[str, Any]
type ResolutionProvider = Callable[[str], tuple[float, ...] | list[float]]

__all__ = [
    "LayerProviderError",
    "LayerProviderNotFoundError",
    "LayerProviderEntry",
    "LayerProviderService",
]


###############################################################################
class LayerProviderError(Exception):
    """Base exception raised when a layer provider cannot fulfill a request."""


###############################################################################
class LayerProviderNotFoundError(LayerProviderError):
    """Raised when a requested layer does not have a registered provider."""


###############################################################################
class LayerProviderService:
    def __init__(
        self,
        layer_definitions: dict[str, LayerDefinition] | None = None,
        layer_catalog: tuple[GeospatialLayerReferenceEntry, ...] | None = None,
        metadata_provider: ResolutionProvider | None = None,
    ) -> None:
        self.metadata_provider = metadata_provider
        resolved_catalog = layer_catalog
        if resolved_catalog is None and layer_definitions is None:
            try:
                from server.repositories.database.backend import get_database

                repository = ReferenceCatalogRepository(get_database().backend)
                resolved_catalog = repository.load_geospatial_layer_catalog()
            except Exception:
                resolved_catalog = tuple()
        self.layer_definitions = self._build_entries(
            layer_definitions=layer_definitions,
            layer_catalog=resolved_catalog or tuple(),
        )
        self.alias_lookup = self._build_alias_index(self.layer_definitions)

    # -------------------------------------------------------------------------
    def _build_entries(
        self,
        *,
        layer_definitions: dict[str, LayerDefinition] | None,
        layer_catalog: tuple[GeospatialLayerReferenceEntry, ...],
    ) -> dict[str, LayerProviderEntry]:
        entries: dict[str, LayerProviderEntry] = {}
        if layer_definitions is not None:
            for name, specification in layer_definitions.items():
                provider = str(specification.get("provider") or "").strip().lower()
                if not provider:
                    continue
                label = str(specification.get("label") or name).strip()
                aliases = tuple(
                    str(value).strip()
                    for value in specification.get("aliases", ())
                    if str(value).strip()
                )
                resolution_value = self._resolve_resolution(name)
                entries[name] = LayerProviderEntry(
                    name=name,
                    provider=provider,
                    label=label,
                    aliases=aliases,
                    provider_name=str(specification.get("provider_name") or name).strip()
                    or name,
                    resolution_m=resolution_value,
                )
            return entries
        for item in layer_catalog:
            resolution_value = self._resolve_resolution(item.layer_id)
            provider_name = (
                "MODIS_Combined_Thermal_Anomalies_All"
                if item.layer_id == "MODIS_Combined_Thermal_Anomalies_Fire"
                else item.layer_id
            )
            entries[item.layer_id] = LayerProviderEntry(
                name=item.layer_id,
                provider=str(item.provider or "").strip().lower(),
                label=item.display_name,
                aliases=item.aliases,
                provider_name=provider_name,
                resolution_m=resolution_value,
            )
        return entries

    # -------------------------------------------------------------------------
    def _resolve_resolution(self, layer_name: str) -> float | None:
        if self.metadata_provider is None:
            return None
        try:
            values = self.metadata_provider(layer_name)
        except Exception:
            return None
        if not values:
            return None
        normalized: list[float] = []
        for value in values:
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            if numeric > 0:
                normalized.append(numeric)
        if not normalized:
            return None
        return min(normalized)

    # -------------------------------------------------------------------------
    def _build_alias_index(
        self, entries: dict[str, LayerProviderEntry]
    ) -> dict[str, str]:
        lookup: dict[str, str] = {}
        for entry in entries.values():
            lookup[entry.name.lower()] = entry.name
            lookup[entry.label.lower()] = entry.name
            for alias in entry.aliases:
                lookup[alias.lower()] = entry.name
        return lookup

    # -------------------------------------------------------------------------
    def list_options(self) -> dict[str, str]:
        return {entry.name: entry.label for entry in self.layer_definitions.values()}

    # -------------------------------------------------------------------------
    def resolve(self, value: str) -> LayerProviderEntry:
        normalized = (value or "").strip()
        if not normalized:
            raise LayerProviderNotFoundError("Layer selection is required.")
        key = normalized.lower()
        canonical = self.alias_lookup.get(key)
        if canonical is None:
            raise LayerProviderNotFoundError(f"Layer '{normalized}' is not available.")
        return self.layer_definitions[canonical]

    # -------------------------------------------------------------------------
    def describe(self, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            entry = self.resolve(value)
        except LayerProviderError:
            return value
        return entry.label


def build_geospatial_layer_catalog(database: DatabaseBackend) -> LayerProviderService:
    repository = ReferenceCatalogRepository(database)
    return LayerProviderService(layer_catalog=repository.load_geospatial_layer_catalog())

