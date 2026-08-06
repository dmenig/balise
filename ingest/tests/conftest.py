"""Ingest test fixtures: golden-file loaders and the real PostGIS database (docs/13)."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def load_json() -> object:
    def _load(name: str) -> Any:
        return json.loads((FIXTURES / name).read_text(encoding="utf-8"))

    return _load


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


# --- PostGIS integration fixtures -------------------------------------------------


REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "api" / "alembic.ini"
TABLES_TO_CLEAR = (
    "observation",
    "spot_status",
    "field_status",
    "conflation_log",
    "spot",
    "field",
    "harbour",
    "nav_aid",
    "source",
    "shom_feature",
    "osm_feature",
    "zmel_feature",
)


@pytest.fixture(scope="session")
def ingest_database_url(test_database_exists: None) -> Iterator[str]:
    provided = os.environ.get("BALISE_TEST_DATABASE_URL")
    if provided:
        os.environ["DATABASE_URL"] = provided
        yield provided
        return
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgis/postgis:16-3.4", driver="psycopg") as container:
        url = container.get_connection_url()
        os.environ["DATABASE_URL"] = url
        yield url


@pytest.fixture(scope="session")
def migrated(ingest_database_url: str) -> Iterator[str]:
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
    yield ingest_database_url


@pytest.fixture
def session_sync(migrated: str) -> Iterator[Session]:
    from balise_api.config import get_settings

    engine = create_engine(get_settings().sync_database_url)
    maker = sessionmaker(engine, expire_on_commit=False)
    with maker() as session:
        yield session
        session.rollback()
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {', '.join(TABLES_TO_CLEAR)} RESTART IDENTITY CASCADE"))
        connection.execute(text("UPDATE meta SET value = '0' WHERE key = 'ref_version'"))
        connection.execute(text("DELETE FROM meta WHERE key LIKE 'counts:%'"))
    engine.dispose()
