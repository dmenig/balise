"""Shared bootstrap for the suites that talk to a real PostGIS (docs/13).

A clean clone runs `make up && make check`, so the test database is created here rather than being a
step in a document that nobody reads. When `BALISE_TEST_DATABASE_URL` is unset, each suite starts a
testcontainer instead and this is a no-op.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text


@pytest.fixture(scope="session", autouse=True)
def test_database_exists() -> None:
    url = os.environ.get("BALISE_TEST_DATABASE_URL")
    if not url:
        return
    server, _, name = url.rpartition("/")
    engine = create_engine(f"{server}/postgres", isolation_level="AUTOCOMMIT")
    with engine.connect() as connection:
        found = connection.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}
        ).scalar_one_or_none()
        if found is None:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
    engine.dispose()
