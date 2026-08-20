from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from server.api.chat import get_models, pull_ollama_model
from server.contracts.chat import OllamaPullRequest

###############################################################################
class _FailingModelLibrary:

    # -------------------------------------------------------------------------
    def list_models(self, **kwargs):  # noqa: ANN003
        _ = kwargs
        raise RuntimeError(
            "api-key=sk-test https://provider.invalid/v1 C:\\private\\models.json"
        )

###############################################################################
class _FailingMaintenance:

    # -------------------------------------------------------------------------
    def pull_ollama_model(self, payload):  # noqa: ANN001
        _ = payload
        raise RuntimeError(
            "api-key=sk-test https://ollama.invalid/api C:\\private\\ollama.log"
        )

###############################################################################
def test_model_catalog_exception_has_stable_public_message() -> None:
    runtime = SimpleNamespace(
        model_library_service=_FailingModelLibrary(),
        settings_service=SimpleNamespace(get_ollama_url=lambda: "http://ollama.invalid"),
    )

    with pytest.raises(HTTPException) as raised:
        get_models(runtime=runtime)  # type: ignore[arg-type]

    assert raised.value.detail == "Could not load cloud models."
    assert "sk-test" not in str(raised.value.detail)
    assert "provider.invalid" not in str(raised.value.detail)
    assert "models.json" not in str(raised.value.detail)

###############################################################################
def test_ollama_pull_exception_has_stable_public_message() -> None:
    runtime = SimpleNamespace(maintenance_service=_FailingMaintenance())

    with pytest.raises(HTTPException) as raised:
        pull_ollama_model(
            OllamaPullRequest(model="test-model"),
            runtime=runtime,  # type: ignore[arg-type]
        )

    assert raised.value.detail == "Ollama pull failed."
    assert "sk-test" not in str(raised.value.detail)
    assert "ollama.invalid" not in str(raised.value.detail)
    assert "ollama.log" not in str(raised.value.detail)
