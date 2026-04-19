from __future__ import annotations

import json
import os
from typing import Any

from AEGIS.server.common.constants import PROJECT_DIR

type JsonDict = dict[str, Any]


class ManifestValidationError(ValueError):
    pass


class GeospatialManifestLoader:
    REQUIRED_FIELDS = {
        "id",
        "name",
        "provider",
        "type",
        "description",
        "capabilities",
        "coverage",
        "version",
        "last_modified",
        "metadata",
    }

    def __init__(self, root_path: str | None = None) -> None:
        base = root_path or os.path.join(PROJECT_DIR, "resources", "manifests")
        self.root_path = os.path.abspath(base)
        self.index_path = os.path.join(self.root_path, "index.json")

    def _load_json(self, path: str) -> Any:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def load_index(self) -> JsonDict:
        payload = self._load_json(self.index_path)
        if not isinstance(payload, dict):
            raise ManifestValidationError("Manifest index must be an object.")
        return payload

    def _validate_entry(
        self, entry: JsonDict, *, source: str, source_path: str | None = None
    ) -> JsonDict:
        missing = [field for field in self.REQUIRED_FIELDS if field not in entry]
        if missing:
            raise ManifestValidationError(
                f"Manifest '{source}' entry '{entry.get('id')}' is missing fields: {', '.join(sorted(missing))}"
            )
        normalized = dict(entry)
        normalized["capabilities"] = list(entry.get("capabilities") or [])
        metadata = dict(entry.get("metadata") or {})
        normalized["metadata"] = metadata
        normalized["source_filename"] = source
        if source_path:
            normalized["source_path"] = os.path.abspath(source_path)
        return normalized

    def _load_directory_entries(self, relative_dir: str) -> list[JsonDict]:
        folder = os.path.join(self.root_path, relative_dir)
        if not os.path.isdir(folder):
            return []
        entries: list[JsonDict] = []
        for filename in sorted(os.listdir(folder)):
            if not filename.lower().endswith(".json"):
                continue
            path = os.path.join(folder, filename)
            payload = self._load_json(path)
            if not isinstance(payload, dict):
                raise ManifestValidationError(
                    f"Manifest document '{path}' must be an object."
                )
            entries.append(
                self._validate_entry(payload, source=filename, source_path=path)
            )
        return entries

    def load_all(self) -> JsonDict:
        index = self.load_index()
        providers = self._load_directory_entries(
            str(index.get("providers_dir") or "providers")
        )
        basemaps = self._load_directory_entries(
            str(index.get("basemaps_dir") or "basemaps")
        )
        overlays = self._load_directory_entries(
            str(index.get("overlays_dir") or "overlays")
        )
        return {
            "providers": providers,
            "basemaps": basemaps,
            "overlays": overlays,
        }
