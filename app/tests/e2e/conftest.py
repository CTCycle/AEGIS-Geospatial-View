"""Bound Chromium startup for browser diagnostics and the E2E suite."""

from typing import Any

import pytest


@pytest.fixture(scope="session")
def browser_type_launch_args(
    browser_type_launch_args: dict[str, Any],
) -> dict[str, Any]:
    return {**browser_type_launch_args, "timeout": 60_000}
