from __future__ import annotations

import pytest

###############################################################################
@pytest.fixture(autouse=True)
def offline_models_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests never reach models.dev; the static OpenCode table applies."""

    monkeypatch.setattr(
        "server.services.llm.opencode_provider.fetch_models_dev_entries",
        lambda provider, policy: {},
    )
