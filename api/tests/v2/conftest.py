"""The v2 suite runs with availability switched on — the M3 wiring, exercised (docs/14)."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture(scope="session", autouse=True)
def availability_enabled() -> None:
    os.environ["FEATURE_AVAILABILITY"] = "true"


@pytest.fixture
async def client(migrated_database: str, availability_enabled: None) -> AsyncIterator[AsyncClient]:
    """A client whose app has the real provider and the real availability routers wired."""
    import importlib

    from balise_api import main as main_module

    importlib.reload(main_module)
    app = main_module.create_app()
    assert app.state.availability_enabled, "the v2 suite must run with the flag on"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    from balise_api.db import dispose_engine

    await dispose_engine()
