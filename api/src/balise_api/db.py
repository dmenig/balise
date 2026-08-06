from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from balise_api.config import get_settings


def _async_url(url: str) -> str:
    return url.replace("postgresql://", "postgresql+psycopg://")


def make_async_engine(url: str | None = None) -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        _async_url(url or settings.database_url),
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=10,
        echo=False,
    )


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = make_async_engine()
    return _engine


def session_factory() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(engine(), expire_on_commit=False)
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory()() as session:
        yield session


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    async with session_factory()() as session:
        yield session


@contextmanager
def sync_session(url: str | None = None) -> Iterator[Session]:
    """Synchronous session — used by the ingest CLI and the admin CLI, never by the API."""
    settings = get_settings()
    sync_engine = create_engine(url or settings.sync_database_url, pool_pre_ping=True)
    maker = sessionmaker(sync_engine, expire_on_commit=False)
    with maker() as session:
        yield session
    sync_engine.dispose()


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
