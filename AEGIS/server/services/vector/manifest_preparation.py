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
        "keywords",
        "intent_tags",
        "task_tags",
        "map_type_tags",
        "primary_use_cases",
        "search_examples",
        "disambiguation_notes",
        "integration_requirements",
    )
    REQUIRED_METADATA_STRING_FIELDS = ("human_summary", "location_dependency")

    def _normalize_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    def validate_embedding_quality(self, entry: dict[str, Any], *, kind: str) -> None:
        source = str(entry.get("source_filename") or entry.get("id") or "unknown")
        missing: list[str] = []
        for field in self.REQUIRED_TEXT_FIELDS:
            if (
                not isinstance(entry.get(field), str)
                or not str(entry.get(field)).strip()
            ):
                missing.append(field)
        metadata = dict(entry.get("metadata") or {})
        for field in self.REQUIRED_METADATA_STRING_FIELDS:
            if (
                not isinstance(metadata.get(field), str)
                or not str(metadata.get(field)).strip()
            ):
                missing.append(f"metadata.{field}")
        for field in self.REQUIRED_METADATA_LIST_FIELDS:
            if not self._normalize_list(metadata.get(field)):
                missing.append(f"metadata.{field}")
        if missing:
            manifest_kind = kind[:-1] if kind.endswith("s") else kind
            raise ManifestEmbeddingValidationError(
                f"Manifest '{source}' ({manifest_kind}:{entry.get('id')}) is missing embedding-critical fields: "
                + ", ".join(sorted(missing))
            )

    def compose_embedding_text(self, entry: dict[str, Any], kind: str) -> str:
        metadata = dict(entry.get("metadata") or {})
        kind_label = kind[:-1] if kind.endswith("s") else kind
        lines = [
            f"Resource type: {kind_label}",
            f"Name: {entry.get('name') or 'Unknown resource'}",
            f"Provider: {entry.get('provider') or 'Unknown provider'}",
            f"Description: {entry.get('description') or 'No description provided.'}",
        ]
        if entry.get("coverage"):
            lines.append(f"Coverage: {entry['coverage']}")
        for label, key in (
            ("Capabilities", "capabilities"),
            ("Keywords", "keywords"),
            ("Intent tags", "intent_tags"),
            ("Task tags", "task_tags"),
            ("Map styles", "map_type_tags"),
            ("Primary use cases", "primary_use_cases"),
            ("Search examples", "search_examples"),
            ("Disambiguation notes", "disambiguation_notes"),
            ("Integration requirements", "integration_requirements"),
        ):
            values = self._normalize_list(
                entry.get(key) if key == "capabilities" else metadata.get(key)
            )
            if values:
                lines.append(f"{label}: {', '.join(values)}")
        if (
            isinstance(metadata.get("human_summary"), str)
            and metadata["human_summary"].strip()
        ):
            lines.append(f"Human summary: {metadata['human_summary'].strip()}")
        if (
            isinstance(metadata.get("location_dependency"), str)
            and metadata["location_dependency"].strip()
        ):
            lines.append(
                f"Location dependency: {metadata['location_dependency'].strip()}"
            )
        if (
            isinstance(metadata.get("temporal_behavior"), str)
            and metadata["temporal_behavior"].strip()
        ):
            lines.append(f"Temporal behavior: {metadata['temporal_behavior'].strip()}")
        return "\n".join(lines).strip()

    def compose_chunk_metadata(
        self, entry: dict[str, Any], kind: str
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
            "keywords": ",".join(self._normalize_list(metadata.get("keywords"))),
            "source_path": entry.get("source_path"),
            "source_filename": entry.get("source_filename"),
        }

    def prepare_entry(self, entry: dict[str, Any], kind: str) -> PreparedManifestChunk:
        self.validate_embedding_quality(entry, kind=kind)
        entry_id = str(entry.get("id") or "").strip()
        if not entry_id:
            raise ManifestEmbeddingValidationError(
                "Manifest entry is missing a stable id."
            )
        return PreparedManifestChunk(
            id=f"{kind}:{entry_id}",
            text=self.compose_embedding_text(entry, kind),
            metadata=self.compose_chunk_metadata(entry, kind),
        )
