from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from server.common.paths import PROJECT_DIR
from server.domain.geographics import CapabilityManifestV2

type JsonDict = dict[str, Any]


###############################################################################
class ManifestValidationError(ValueError):
    pass


###############################################################################
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
    REQUIRED_SCHEMA_V2_FIELDS = {
        "capabilityKind",
        "renderingMode",
        "sourceOfficialDocs",
        "license",
        "auth",
        "agenticUse",
        "reliability",
        "cachePolicy",
        "normalization",
    }

    # -------------------------------------------------------------------------
    def __init__(self, root_path: str | Path | None = None) -> None:
        base_path = (
            Path(root_path)
            if root_path is not None
            else PROJECT_DIR / "resources" / "catalog"
        )
        resolved_root = base_path.resolve()
        self.root_path = str(resolved_root)
        self.index_path = resolved_root / "index.json"

    # -------------------------------------------------------------------------
    def _load_json(self, path: str | Path) -> Any:
        with Path(path).open("r", encoding="utf-8") as handle:
            return json.load(handle)

    # -------------------------------------------------------------------------
    def load_index(self) -> JsonDict:
        payload = self._load_json(self.index_path)
        if not isinstance(payload, dict):
            raise ManifestValidationError("Manifest index must be an object.")
        return payload

    # -------------------------------------------------------------------------
    def _validate_entry(
        self, entry: JsonDict, *, source: str, source_path: str | Path | None = None
    ) -> JsonDict:
        missing = [
            field
            for field in sorted(self.REQUIRED_FIELDS | self.REQUIRED_SCHEMA_V2_FIELDS)
            if field not in entry
        ]
        if missing:
            raise ManifestValidationError(
                f"Manifest '{source}' entry '{entry.get('id')}' is missing fields: {', '.join(sorted(missing))}"
            )
        try:
            CapabilityManifestV2.model_validate(entry)
        except ValidationError as exc:
            raise ManifestValidationError(
                f"Manifest '{source}' entry '{entry.get('id')}' failed schema v2 validation: {exc}"
            ) from exc
        normalized = dict(entry)
        normalized["capabilities"] = list(entry.get("capabilities") or [])
        normalized["metadata"] = dict(entry.get("metadata") or {})
        normalized["source_filename"] = source
        if source_path:
            normalized["source_path"] = str(Path(source_path).resolve())
        return normalized

    # -------------------------------------------------------------------------
    def _load_directory_entries(self, relative_dir: str) -> list[JsonDict]:
        folder = Path(self.root_path) / relative_dir
        if not folder.is_dir():
            return []
        entries: list[JsonDict] = []
        for path in sorted(folder.iterdir()):
            if path.suffix.lower() != ".json":
                continue
            payload = self._load_json(path)
            if not isinstance(payload, dict):
                raise ManifestValidationError(
                    f"Manifest document '{path}' must be an object."
                )
            entries.append(
                self._validate_entry(payload, source=path.name, source_path=path)
            )
        return entries

    # -------------------------------------------------------------------------
    def _load_runtime_profiles(self, filename: str) -> list[JsonDict]:
        path = Path(self.root_path) / filename
        payload = self._load_json(path)
        if not isinstance(payload, dict):
            raise ManifestValidationError("Runtime profiles must be an object.")
        profiles = payload.get("profiles")
        if not isinstance(profiles, list):
            raise ManifestValidationError("Runtime profiles must contain a profiles list.")
        normalized: list[JsonDict] = []
        for item in profiles:
            if not isinstance(item, dict):
                raise ManifestValidationError("Runtime profile entries must be objects.")
            capability_id = str(item.get("capability_id") or "").strip()
            if not capability_id:
                raise ManifestValidationError("Runtime profile entry missing capability_id.")
            normalized.append(dict(item))
        return normalized

    # -------------------------------------------------------------------------
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
        tools = self._load_directory_entries(str(index.get("tools_dir") or "tools"))
        cameras = self._load_directory_entries(
            str(index.get("cameras_dir") or "cameras")
        )
        transit = self._load_directory_entries(
            str(index.get("transit_dir") or "transit")
        )
        runtime_profiles = self._load_runtime_profiles(
            str(index.get("runtime_profiles_file") or "runtime_profiles.json")
        )
        return {
            "providers": providers,
            "basemaps": basemaps,
            "overlays": overlays,
            "cameras": cameras,
            "transit": transit,
            "tools": tools,
            "runtime_profiles": runtime_profiles,
        }
