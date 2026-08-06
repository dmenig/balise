from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from balise_api.domain.enums import SourceKind, SpotKind
from balise_api.models import Feed, Field, Observation, Spot
from balise_api.repositories.protocols import (
    FeedNotFound,
    FeedRef,
    FieldNotFound,
    FieldRef,
    SpotNotFound,
    SpotRef,
)


class SqlFeedRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _row(self, feed_id: str) -> Feed:
        row = await self._session.get(Feed, feed_id)
        if row is None or not row.active:
            raise FeedNotFound(f"feed {feed_id}")
        return row

    async def get(self, feed_id: str) -> FeedRef:
        row = await self._row(feed_id)
        return FeedRef(
            id=row.id,
            harbour_id=row.harbour_id,
            kind=SourceKind(row.kind),
            trust=float(row.trust),
            ttl_seconds=row.ttl_seconds,
            active=row.active,
            last_seen_at=row.last_seen_at,
        )

    async def token_hash(self, feed_id: str) -> str:
        return (await self._row(feed_id)).token_hash

    async def touch(self, feed_id: str, *, accepted: int, rejected: int, at: datetime) -> None:
        row = await self._row(feed_id)
        row.last_seen_at = at
        row.accepted_24h += accepted
        row.rejected_24h += rejected

    async def resolve_spot(self, feed: FeedRef, external_id: str) -> SpotRef:
        """Match the vendor's own berth id, or fall back to the painted code in that harbour."""
        stmt = (
            select(
                Spot.id,
                Spot.kind,
                func.ST_X(Spot.geom).label("lon"),
                func.ST_Y(Spot.geom).label("lat"),
                Spot.field_id,
                Spot.harbour_id,
                Spot.code,
            )
            .where(
                Spot.active,
                or_(
                    Spot.external_ids[feed.id].astext == external_id,
                    (Spot.harbour_id == feed.harbour_id) & (Spot.code == external_id),
                ),
            )
            .limit(1)
        )
        row = (await self._session.execute(stmt)).one_or_none()
        if row is None:
            raise SpotNotFound(f"spot {external_id!r} for feed {feed.id}")
        return SpotRef(
            id=row.id,
            kind=SpotKind(row.kind),
            lon=float(row.lon),
            lat=float(row.lat),
            field_id=row.field_id,
            harbour_id=row.harbour_id,
            code=row.code,
        )

    async def resolve_field(self, feed: FeedRef, external_id: str) -> FieldRef:
        stmt = (
            select(Field.id, Field.kind, Field.capacity, Field.harbour_id)
            .where(
                or_(
                    Field.external_ids[feed.id].astext == external_id,
                    (Field.harbour_id == feed.harbour_id) & (Field.name == external_id),
                )
            )
            .limit(1)
        )
        row = (await self._session.execute(stmt)).one_or_none()
        if row is None:
            raise FieldNotFound(f"field {external_id!r} for feed {feed.id}")
        return FieldRef(
            id=row.id, kind=SpotKind(row.kind), capacity=row.capacity, harbour_id=row.harbour_id
        )

    async def health(self, feed_id: str, now: datetime) -> dict[str, Any]:
        row = await self._row(feed_id)
        staleness = (now - row.last_seen_at).total_seconds() if row.last_seen_at else None
        total = row.accepted_24h + row.rejected_24h
        window_start = now - timedelta(hours=24)
        observed = await self._session.execute(
            select(func.count()).where(
                Observation.source_ref == feed_id, Observation.received_at >= window_start
            )
        )
        return {
            "feed_id": feed_id,
            "last_received": row.last_seen_at,
            "ttl_seconds": row.ttl_seconds,
            "staleness_seconds": staleness,
            "stale": staleness is not None and staleness > 3 * row.ttl_seconds,
            "observations_24h": int(observed.scalar_one()),
            "accepted_24h": row.accepted_24h,
            "rejected_24h": row.rejected_24h,
            "rejection_rate_24h": round(row.rejected_24h / total, 3) if total else 0.0,
        }
