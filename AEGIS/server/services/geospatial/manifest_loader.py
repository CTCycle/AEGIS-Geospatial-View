from __future__ import annotations

import json
import os
from typing import Any

from AEGIS.server.utils.constants import PROJECT_DIR

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
        "metadata",
    }

    def __init__(self, root_path: str | None = None) -> None:
        base = root_path or os.path.join(PROJECT_DIR, "resources", "manifests")
        self.root_path = os.path.abspath(base)
        self.index_path = os.path.join(self.root_path, "index.json")

    def _load_json_file(self, filename: str) -> list[JsonDict] | JsonDict:
        path = os.path.join(self.root_path, filename)
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def _validate_entry(self, entry: JsonDict, *, filename: str) -> JsonDict:
        missing = [field for field in self.REQUIRED_FIELDS if field not in entry]
        if missing:
            raise ManifestValidationError(
                f"Manifest '{filename}' entry '{entry.get('id')}' is missing fields: {', '.join(sorted(missing))}"
            )
        normalized = dict(entry)
        normalized["capabilities"] = list(entry.get("capabilities") or [])
        normalized["metadata"] = dict(entry.get("metadata") or {})
        return normalized

    def _load_manifest(self, filename: str) -> list[JsonDict]:
        payload = self._load_json_file(filename)
        if not isinstance(payload, list):
            raise ManifestValidationError(f"Manifest '{filename}' must contain an array.")
        normalized: list[JsonDict] = []
        for entry in payload:
            if not isinstance(entry, dict):
                raise ManifestValidationError(f"Manifest '{filename}' contains non-object entries.")
            normalized.append(self._validate_entry(entry, filename=filename))
        return normalized

    def load_index(self) -> JsonDict:
        payload = self._load_json_file("index.json")
        if not isinstance(payload, dict):
            raise ManifestValidationError("Manifest index must be an object.")
        return dict(payload)

    def load_all(self) -> JsonDict:
        index = self.load_index()
        providers_file = str(index.get("providers") or "providers.json")
        basemaps_file = str(index.get("basemaps") or "basemaps.json")
        overlays_file = str(index.get("overlays") or "overlays.json")
        return {
            "providers": self._load_manifest(providers_file),
            "basemaps": self._load_manifest(basemaps_file),
            "overlays": self._load_manifest(overlays_file),
        }
