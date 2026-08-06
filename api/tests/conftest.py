"""Integration fixtures: a **real PostGIS** database (docs/13 — spatial SQL must not be mocked).

`BALISE_TEST_DATABASE_URL` points the suite at an existing database (the compose one locally, a
service container in CI). Without it, a `postgis/postgis:16-3.4` testcontainer is started.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "api" / "alembic.ini"
TABLES_TO_CLEAR = (
    "observation",
    "spot_status",
    "field_status",
    "comment",
    "issue",
    "contributor",
    "feed",
    "tide_prediction",
    "weather_forecast",
    "spot",
    "field",
    "harbour",
    "nav_aid",
    "conflation_log",
    "source",
)


def _testcontainer_url() -> Iterator[str]:
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgis/postgis:16-3.4", driver="psycopg") as container:
        yield container.get_connection_url()


@pytest.fixture(scope="session")
def database_url(test_database_exists: None) -> Iterator[str]:
    # Tests must never read the development tile cache, so they use their own Redis database.
    os.environ.setdefault(
        "REDIS_URL", os.environ.get("BALISE_TEST_REDIS_URL", "redis://localhost:6379/1")
    )
    # The whole suite shares one client IP, so the real 60/min limit would throttle the tests
    # themselves. The limiter has its own dedicated test with a low limit.
    os.environ.setdefault("RATE_LIMIT_ANONYMOUS_PER_MIN", "100000")
    provided = os.environ.get("BALISE_TEST_DATABASE_URL")
    if provided:
        yield provided
        return
    yield from _testcontainer_url()


@pytest.fixture(scope="session", autouse=True)
def migrated_database(database_url: str) -> Iterator[str]:
    """Run the real migrations: the schema under test is the schema we ship."""
    os.environ["DATABASE_URL"] = database_url
    from balise_api.config import get_settings

    get_settings.cache_clear()
    engine = create_engine(get_settings().sync_database_url)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()

    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_INI.parent / "alembic"))
    command.upgrade(config, "head")
    yield database_url


@pytest.fixture
async def session(migrated_database: str) -> AsyncIterator[AsyncSession]:
    from balise_api.config import get_settings

    engine = create_async_engine(get_settings().database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    async with engine.begin() as connection:
        await connection.execute(
            text(f"TRUNCATE {', '.join(TABLES_TO_CLEAR)} RESTART IDENTITY CASCADE")
        )
        await connection.execute(text("UPDATE meta SET value = '0' WHERE key = 'ref_version'"))
        await connection.execute(text("DELETE FROM meta WHERE key LIKE 'counts:%'"))
    await engine.dispose()


@pytest.fixture
async def client(migrated_database: str) -> AsyncIterator[AsyncClient]:
    from balise_api.config import get_settings
    from balise_api.main import create_app

    settings = get_settings()
    settings.feature_websocket = False  # no relay tasks inside the test event loop
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    from balise_api.db import dispose_engine

    await dispose_engine()
