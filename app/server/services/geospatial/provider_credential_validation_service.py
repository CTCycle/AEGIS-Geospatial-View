from __future__ import annotations

from collections.abc import Mapping

from server.domain.geographics import ProviderCredentialValidationResult
from server.services.geospatial.provider_account_setup_service import (
    ProviderAccountSetupService,
)
from server.services.geospatial.provider_registry import (
    ProviderNotRegisteredError,
    ProviderRegistry,
)
from server.services.geospatial.providers.base import ProviderAuthError, ProviderError
from server.services.geospatial.runtime_registry import RuntimeRegistry


class ProviderCredentialValidationService:
    def __init__(
        self,
        runtime_registry: RuntimeRegistry | None = None,
        provider_registry: ProviderRegistry | None = None,
    ) -> None:
        self.runtime_registry = runtime_registry or RuntimeRegistry()
        self.provider_registry = provider_registry or ProviderRegistry(
            manifest_loader=self.runtime_registry.manifest_loader
        )
        self.setup_service = ProviderAccountSetupService(self.runtime_registry)

    async def validate(
        self,
        provider_id: str,
        credentials: Mapping[str, str],
    ) -> ProviderCredentialValidationResult:
        setup = self.setup_service.get_setup(provider_id)
        if setup.mode == "not_required":
            return ProviderCredentialValidationResult(
                provider_id=setup.provider_id,
                valid=True,
                status="valid",
                message="No access key is required for this provider.",
            )
        missing = [
            field.label
            for field in setup.credential_fields
            if field.required and not credentials.get(field.name, "").strip()
        ]
        if missing:
            return ProviderCredentialValidationResult(
                provider_id=setup.provider_id,
                valid=False,
                status="invalid",
                message=f"Missing required credential field: {', '.join(missing)}.",
            )
        self.provider_registry.build_from_manifests()
        try:
            provider = self.provider_registry.get(setup.provider_id)
        except ProviderNotRegisteredError:
            raise
        validate_credentials = getattr(provider, "validate_credentials", None)
        if not callable(validate_credentials):
            return ProviderCredentialValidationResult(
                provider_id=setup.provider_id,
                valid=False,
                status="unsupported",
                message="Credential validation is not implemented for this provider.",
            )
        try:
            return await validate_credentials(dict(credentials))
        except ProviderAuthError:
            return ProviderCredentialValidationResult(
                provider_id=setup.provider_id,
                valid=False,
                status="invalid",
                message="Provider rejected the supplied credential.",
            )
        except ProviderError:
            return ProviderCredentialValidationResult(
                provider_id=setup.provider_id,
                valid=False,
                status="error",
                message="Provider credential validation failed due to a provider error.",
            )
