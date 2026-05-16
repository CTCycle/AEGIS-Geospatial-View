from __future__ import annotations

from server.services.geospatial.provider_account_setup_service import (
    ProviderAccountSetupService,
)
from server.services.geospatial.provider_registry import ProviderNotRegisteredError


def test_provider_account_setup_returns_manifest_defined_setup() -> None:
    setup = ProviderAccountSetupService().get_setup("geoapify")

    assert setup.provider_id == "geoapify"
    assert setup.mode == "manual"
    assert setup.credential_fields[0].name == "api_key"
    assert setup.automation_supported is False


def test_provider_account_setup_returns_not_required_for_no_key_provider() -> None:
    setup = ProviderAccountSetupService().get_setup("openmeteo")

    assert setup.mode == "not_required"
    assert setup.credential_fields == []
    assert setup.steps == []


def test_provider_account_setup_does_not_include_stored_values() -> None:
    setup = ProviderAccountSetupService().get_setup("tomtom")

    dumped = setup.model_dump_json()
    assert "api_key" in dumped
    assert "TOMTOM_API_KEY" not in dumped
    assert "tomtom-secret" not in dumped


def test_provider_account_setup_raises_for_unknown_provider() -> None:
    service = ProviderAccountSetupService()

    try:
        service.get_setup("missing-provider")
    except ProviderNotRegisteredError:
        pass
    else:
        raise AssertionError("Unknown provider unexpectedly resolved.")
