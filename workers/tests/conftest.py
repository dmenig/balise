from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "api" / "alembic.ini"
TABLES_TO_CLEAR = (
    "observation",
    "spot_status",
    "field_status",
    "contributor",
    "feed",
    "spot",
    "field",
    "harbour",
    "nav_aid",
    "source",
)


@pytest.fixture(scope="session")
def worker_database_url(test_database_exists: None) -> Iterator[str]:
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
def migrated_worker_db(worker_database_url: str) -> Iterator[str]:
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
    yield worker_database_url


@pytest.fixture
def session(migrated_worker_db: str) -> Iterator[Session]:
    from balise_api.config import get_settings

    engine = create_engine(get_settings().sync_database_url)
    maker = sessionmaker(engine, expire_on_commit=False)
    with maker() as session:
        yield session
        session.rollback()
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {', '.join(TABLES_TO_CLEAR)} RESTART IDENTITY CASCADE"))
    engine.dispose()
