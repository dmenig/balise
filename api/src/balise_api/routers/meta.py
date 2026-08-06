from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from sqlalchemy import text

from balise_api import cache
from balise_api.auth.dependencies import SessionDep
from balise_api.config import get_settings

router = APIRouter(tags=["ops"])

_DATA_HEALTH_SQL = """
SELECT s.id, s.kind::text AS kind, s.last_sync_at,
       (SELECT count(*) FROM nav_aid n WHERE n.source_id = s.id) AS nav_aids,
       (SELECT count(*) FROM spot sp WHERE sp.source_id = s.id) AS spots
FROM source s
ORDER BY s.id
"""

_FEED_HEALTH_SQL = """
SELECT id, last_seen_at, ttl_seconds,
       extract(epoch FROM (now() - last_seen_at)) AS staleness_seconds
FROM feed
WHERE active
"""


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(session: SessionDep) -> dict[str, Any]:
    version = await session.execute(text("SELECT value FROM meta WHERE key = 'ref_version'"))
    ref_version = version.scalar_one_or_none()
    redis_ok = await cache.ping()
    return {
        "status": "ok" if ref_version is not None and redis_ok else "degraded",
        "database": True,
        "redis": redis_ok,
        "ref_version": ref_version,
    }


@router.get("/health/data")
async def data_health(session: SessionDep) -> dict[str, Any]:
    """Data-quality health matters more than infra health here (docs/12)."""
    sources = (await session.execute(text(_DATA_HEALTH_SQL))).all()
    feeds = (await session.execute(text(_FEED_HEALTH_SQL))).all()
    stale_feeds = [
        row.id
        for row in feeds
        if row.staleness_seconds is None or row.staleness_seconds > 3 * row.ttl_seconds
    ]
    return {
        "checked_at": datetime.now(UTC),
        "env": get_settings().env,
        "sources": [
            {
                "id": row.id,
                "kind": row.kind,
                "last_sync_at": row.last_sync_at,
                "nav_aids": int(row.nav_aids),
                "spots": int(row.spots),
            }
            for row in sources
        ],
        "feeds": {
            "total": len(feeds),
            "stale": stale_feeds,
        },
    }
