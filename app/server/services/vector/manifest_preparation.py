from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PreparedManifestChunk:
    id: str
    text: str
    metadata: dict[str, Any]


class ManifestEmbeddingValidationError(ValueError):
    pass


class ManifestPreparationService:
    REQUIRED_TEXT_FIELDS = ("description",)
    REQUIRED_METADATA_LIST_FIELDS = (
        "action_tags",
        "task_tags",
        "search_examples",
    )

    def _normalize_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    def _backfill_embedding_fields(self, entry: dict[str, Any], *, kind: str) -> None:
        entry_id = str(entry.get("id") or "resource").strip() or "resource"
        name = str(entry.get("name") or entry_id).strip() or entry_id
        provider = str(entry.get("provider") or "unknown provider").strip() or "unknown provider"
        if not isinstance(entry.get("description"), str) or not str(entry.get("description")).strip():
            entry["description"] = f"No description provided for {name}."
        metadata = dict(entry.get("metadata") or {})
        capabilities = self._normalize_list(entry.get("capabilities"))
        if not self._normalize_list(metadata.get("action_tags")):
            metadata["action_tags"] = capabilities[:5] or [kind[:-1] if kind.endswith("s") else kind]
        if not self._normalize_list(metadata.get("task_tags")):
            metadata["task_tags"] = [f"show {name}", f"use {provider} data"]
        if not self._normalize_list(metadata.get("search_examples")):
            metadata["search_examples"] = [
                f"Show {name} on the map",
                f"Find {provider} data for this location",
                f"Use {name} for geospatial analysis",
            ]
        entry["metadata"] = metadata

    def validate_embedding_quality(self, entry: dict[str, Any], *, kind: str) -> None:
        self._backfill_embedding_fields(entry, kind=kind)
        source = str(entry.get("source_filename") or entry.get("id") or "unknown")
        missing: list[str] = []
        for field in self.REQUIRED_TEXT_FIELDS:
            if not isinstance(entry.get(field), str) or not str(entry.get(field)).strip():
                missing.append(field)
        metadata = dict(entry.get("metadata") or {})
        for field in self.REQUIRED_METADATA_LIST_FIELDS:
            if not self._normalize_list(metadata.get(field)):
                missing.append(f"metadata.{field}")
        if missing:
            manifest_kind = kind[:-1] if kind.endswith("s") else kind
            raise ManifestEmbeddingValidationError(
                f"Manifest '{source}' ({manifest_kind}:{entry.get('id')}) is missing embedding-critical fields: "
                + ", ".join(sorted(missing))
            )

    def compose_embedding_text(
        self,
        entry: dict[str, Any],
        kind: str,
        runtime_profile: dict[str, Any] | None = None,
    ) -> str:
        metadata = dict(entry.get("metadata") or {})
        kind_label = kind[:-1] if kind.endswith("s") else kind
        lines = [
            f"Resource type: {kind_label}",
            f"Name: {entry.get('name') or 'Unknown resource'}",
            f"Provider: {entry.get('provider') or 'Unknown provider'}",
            f"Description: {entry.get('description') or 'No description provided.'}",
            f"Coverage: {entry.get('coverage') or 'global'}",
            f"Action tags: {', '.join(self._normalize_list(metadata.get('action_tags')))}",
            f"Task tags: {', '.join(self._normalize_list(metadata.get('task_tags')))}",
            f"Search examples: {', '.join(self._normalize_list(metadata.get('search_examples')))}",
            f"Location dependency: {metadata.get('location_dependency') or 'location-specific'}",
            f"Constraints: {metadata.get('constraints') or 'none'}",
            f"Source protocol: {metadata.get('source_protocol') or 'unspecified'}",
            f"Data format: {metadata.get('data_format') or 'unspecified'}",
            f"Geometry type: {metadata.get('geometry_type') or 'unspecified'}",
            f"Queryable: {bool(metadata.get('queryable', False))}",
            f"Vectorizable: {bool(metadata.get('vectorizable', False))}",
            f"Authentication mode: {metadata.get('auth_mode') or 'none'}",
        ]
        if isinstance(runtime_profile, dict):
            lines.extend(
                [
                    f"Runtime supports map: {bool(runtime_profile.get('supports_map', False))}",
                    f"Runtime supports direct text: {bool(runtime_profile.get('supports_direct_text', False))}",
                    f"Runtime credential provider: {runtime_profile.get('credential_provider') or 'none'}",
                    f"Runtime coverage policy: {runtime_profile.get('coverage_policy') or 'global'}",
                ]
            )
        return "\n".join(lines).strip()

    def compose_chunk_metadata(
        self,
        entry: dict[str, Any],
        kind: str,
        runtime_profile: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        metadata = dict(entry.get("metadata") or {})
        return {
            "id": entry.get("id"),
            "name": entry.get("name"),
            "provider": entry.get("provider"),
            "type": entry.get("type"),
            "document_kind": kind[:-1] if kind.endswith("s") else kind,
            "capabilities": ",".join(self._normalize_list(entry.get("capabilities"))),
            "coverage": entry.get("coverage"),
            "action_tags": ",".join(self._normalize_list(metadata.get("action_tags"))),
            "task_tags": ",".join(self._normalize_list(metadata.get("task_tags"))),
            "runtime_supports_map": bool((runtime_profile or {}).get("supports_map", False)),
            "runtime_supports_direct_text": bool((runtime_profile or {}).get("supports_direct_text", False)),
            "runtime_credential_provider": (runtime_profile or {}).get("credential_provider"),
            "source_protocol": metadata.get("source_protocol"),
            "data_format": metadata.get("data_format"),
            "geometry_type": metadata.get("geometry_type"),
            "queryable": bool(metadata.get("queryable", False)),
            "vectorizable": bool(metadata.get("vectorizable", False)),
            "source_path": entry.get("source_path"),
            "source_filename": entry.get("source_filename"),
        }

    def prepare_entry(
        self,
        entry: dict[str, Any],
        kind: str,
        runtime_profile: dict[str, Any] | None = None,
    ) -> PreparedManifestChunk:
        self.validate_embedding_quality(entry, kind=kind)
        entry_id = str(entry.get("id") or "").strip()
        if not entry_id:
            raise ManifestEmbeddingValidationError("Manifest entry is missing a stable id.")
        return PreparedManifestChunk(
            id=f"{kind}:{entry_id}",
            text=self.compose_embedding_text(entry, kind, runtime_profile=runtime_profile),
            metadata=self.compose_chunk_metadata(entry, kind, runtime_profile=runtime_profile),
        )
