"""The v2 worker suite runs with availability on (docs/14 M3)."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def availability_enabled() -> None:
    os.environ["FEATURE_AVAILABILITY"] = "true"
