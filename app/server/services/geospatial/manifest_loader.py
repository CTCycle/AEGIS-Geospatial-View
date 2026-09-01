from __future__ import annotations

from server.common.typing import is_json_object

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from server.common.paths import PROJECT_DIR, ROOT_DIR
from server.contracts.geospatial import CapabilityManifestV2

type JsonDict = dict[str, Any]


###############################################################################
class CatalogIndex(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    providers_dir: str
    basemaps_dir: str
    overlays_dir: str
    cameras_dir: str
    transit_dir: str
    tools_dir: str
    runtime_profiles_file: str
    manifest_schema_version: int
    source_catalog_version: str
    capability_groups: list[str]
    health_summary: dict[str, int]


###############################################################################
class RuntimeProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_id: str
    enabled_by_default: bool
    credential_provider: str | None
    supports_map: bool
    supports_direct_text: bool
    coverage_policy: str
    health_policy: str
    handler_name: str | None
    capability_kind: str
    rendering_mode: str
    health_status: str
    planner_hints: list[str]
    manual_toggle: bool
    auth_required: bool


###############################################################################
class RuntimeProfilesDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    profiles: list[RuntimeProfile]
    routing_profiles: list[str]


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
    RUNTIME_PROFILE_FRAGMENTS_DIR = "runtime_profiles.d"

    # -------------------------------------------------------------------------
    def __init__(self, root_path: str | Path | None = None) -> None:
        if root_path is None:
            base_path = PROJECT_DIR / "resources" / "catalog"
        else:
            candidate = Path(root_path)
            base_path = candidate if candidate.is_absolute() else ROOT_DIR / candidate
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
        if not is_json_object(payload):
            raise ManifestValidationError("Manifest index must be an object.")
        try:
            return CatalogIndex.model_validate(payload).model_dump()
        except ValidationError as exc:
            raise ManifestValidationError(
                f"Manifest index failed validation: {exc}"
            ) from exc

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
            raise ManifestValidationError(
                f"Manifest directory '{folder}' does not exist."
            )
        entries: list[JsonDict] = []
        for path in sorted(folder.iterdir()):
            if path.suffix.lower() != ".json":
                continue
            payload = self._load_json(path)
            if not is_json_object(payload):
                raise ManifestValidationError(
                    f"Manifest document '{path}' must be an object."
                )
            entries.append(
                self._validate_entry(payload, source=path.name, source_path=path)
            )
        return entries

    # -------------------------------------------------------------------------
    def _load_runtime_profile_fragments(self) -> list[JsonDict]:
        folder = Path(self.root_path) / self.RUNTIME_PROFILE_FRAGMENTS_DIR
        if not folder.exists():
            return []
        if not folder.is_dir():
            raise ManifestValidationError(
                f"Runtime profile fragments path '{folder}' must be a directory."
            )
        profiles: list[JsonDict] = []
        for path in sorted(folder.iterdir()):
            if path.suffix.lower() != ".json":
                continue
            payload = self._load_json(path)
            if not is_json_object(payload):
                raise ManifestValidationError(
                    f"Runtime profile fragment '{path}' must be an object."
                )
            try:
                profile = RuntimeProfile.model_validate(payload)
            except ValidationError as exc:
                raise ManifestValidationError(
                    f"Runtime profile fragment '{path.name}' failed validation: {exc}"
                ) from exc
            profiles.append(profile.model_dump())
        return profiles

    # -------------------------------------------------------------------------
    def _load_runtime_profiles(self, filename: str) -> list[JsonDict]:
        path = Path(self.root_path) / filename
        payload = self._load_json(path)
        if not is_json_object(payload):
            raise ManifestValidationError("Runtime profiles must be an object.")
        try:
            document = RuntimeProfilesDocument.model_validate(payload)
        except ValidationError as exc:
            raise ManifestValidationError(
                f"Runtime profiles failed validation: {exc}"
            ) from exc

        profiles = [profile.model_dump() for profile in document.profiles]
        profiles.extend(self._load_runtime_profile_fragments())
        seen: set[str] = set()
        duplicates: set[str] = set()
        for profile in profiles:
            capability_id = str(profile.get("capability_id") or "").strip()
            if capability_id in seen:
                duplicates.add(capability_id)
            seen.add(capability_id)
        if duplicates:
            raise ManifestValidationError(
                "Duplicate runtime profile capability ids: "
                + ", ".join(sorted(duplicates))
            )
        return profiles

    # -------------------------------------------------------------------------
    def load_all(self) -> JsonDict:
        index = self.load_index()
        providers = self._load_directory_entries(index["providers_dir"])
        basemaps = self._load_directory_entries(index["basemaps_dir"])
        overlays = self._load_directory_entries(index["overlays_dir"])
        tools = self._load_directory_entries(index["tools_dir"])
        cameras = self._load_directory_entries(index["cameras_dir"])
        transit = self._load_directory_entries(index["transit_dir"])
        runtime_profiles = self._load_runtime_profiles(index["runtime_profiles_file"])
        return {
            "providers": providers,
            "basemaps": basemaps,
            "overlays": overlays,
            "cameras": cameras,
            "transit": transit,
            "tools": tools,
            "runtime_profiles": runtime_profiles,
        }
