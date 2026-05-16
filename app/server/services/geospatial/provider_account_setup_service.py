from __future__ import annotations

from typing import Any

from server.domain.geographics import (
    ProviderAccountSetup,
    ProviderAccountSetupStep,
    ProviderCredentialField,
)
from server.services.geospatial.provider_registry import ProviderNotRegisteredError
from server.services.geospatial.runtime_registry import RuntimeRegistry

AUTOMATION_REASON = (
    "Third-party provider signup and key retrieval require external account, "
    "billing, MFA, CAPTCHA, or portal flows that are not stable product APIs."
)


class ProviderAccountSetupService:
    def __init__(self, runtime_registry: RuntimeRegistry | None = None) -> None:
        self.runtime_registry = runtime_registry or RuntimeRegistry()

    def list_setups(self) -> list[ProviderAccountSetup]:
        providers = self._provider_manifests()
        return [self._setup_from_manifest(manifest) for manifest in providers]

    def get_setup(self, provider_id: str) -> ProviderAccountSetup:
        normalized = provider_id.strip().lower()
        for manifest in self._provider_manifests():
            if str(manifest.get("id") or "").strip().lower() == normalized:
                return self._setup_from_manifest(manifest)
        raise ProviderNotRegisteredError(f"Provider '{normalized}' was not found.")

    def _provider_manifests(self) -> list[dict[str, Any]]:
        snapshot = self.runtime_registry.build_snapshot()
        providers = [
            dict(item)
            for item in snapshot.manifests.values()
            if str(item.get("type") or "").strip().lower()
            in {"provider", "credentialed-provider"}
        ]
        return sorted(providers, key=lambda item: str(item.get("name") or item.get("id") or ""))

    def _setup_from_manifest(self, manifest: dict[str, Any]) -> ProviderAccountSetup:
        provider_id = str(manifest.get("id") or "").strip()
        payload = manifest.get("account_setup")
        if isinstance(payload, dict):
            return ProviderAccountSetup(provider_id=provider_id, **payload)
        return self._fallback_setup(provider_id, manifest)

    def _fallback_setup(
        self, provider_id: str, manifest: dict[str, Any]
    ) -> ProviderAccountSetup:
        requires_credentials = _requires_credentials(manifest)
        docs_url = _docs_url(manifest)
        if not requires_credentials:
            return ProviderAccountSetup(
                provider_id=provider_id,
                mode="not_required",
                automation_supported=False,
                automation_reason=None,
                account_url=None,
                dashboard_url=docs_url,
                documentation_url=docs_url,
                credential_fields=[],
                steps=[],
            )
        return ProviderAccountSetup(
            provider_id=provider_id,
            mode="manual",
            automation_supported=False,
            automation_reason=AUTOMATION_REASON,
            account_url=docs_url,
            dashboard_url=docs_url,
            documentation_url=docs_url,
            credential_fields=[
                ProviderCredentialField(
                    name="api_key",
                    label="API key",
                    secret=True,
                    required=True,
                )
            ],
            steps=_manual_steps(),
        )


def _requires_credentials(manifest: dict[str, Any]) -> bool:
    auth = manifest.get("auth")
    return bool(isinstance(auth, dict) and auth.get("required"))


def _docs_url(manifest: dict[str, Any]) -> str | None:
    metadata = manifest.get("metadata")
    if isinstance(metadata, dict):
        for key in ("official_docs_url", "docs_url"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    docs = manifest.get("sourceOfficialDocs")
    if isinstance(docs, list):
        for value in docs:
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _manual_steps() -> list[ProviderAccountSetupStep]:
    return [
        ProviderAccountSetupStep(
            id="create_account",
            title="Create or sign in to the provider account",
            description="Open the provider account page and complete signup or sign in.",
        ),
        ProviderAccountSetupStep(
            id="create_project",
            title="Create or select a project",
            description="Create a project or application in the provider dashboard if required.",
        ),
        ProviderAccountSetupStep(
            id="create_key",
            title="Create an API key",
            description="Generate an API key for the required geospatial APIs.",
        ),
        ProviderAccountSetupStep(
            id="restrict_key",
            title="Restrict the API key",
            description="Apply provider-supported restrictions before saving the key.",
        ),
        ProviderAccountSetupStep(
            id="save_and_validate",
            title="Save and validate in AEGIS",
            description="Paste the key into AEGIS and run validation.",
        ),
    ]
