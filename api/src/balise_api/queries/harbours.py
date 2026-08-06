"""Harbour search and sheet (docs/08).

In v1 the sheet's call to action is the **capitainerie's phone and VHF channel** — the honest
substitute for availability (docs/00). Free counts per field arrive with v2, through the provider.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from balise_api import attribution
from balise_api.domain.enums import SpotKind
from balise_api.repositories.protocols import HarbourNotFound
from balise_api.schemas.harbours import HarbourDetail, HarbourList, HarbourListItem
from balise_api.schemas.spots import FieldSummary
from balise_api.services.availability import AvailabilityProvider

METRES_PER_NM = 1852.0

_SEARCH_SQL = """
SELECT h.id, h.slug, h.name, h.insee_code, ST_X(h.geom) AS lon, ST_Y(h.geom) AS lat,
       CASE WHEN CAST(:lon AS float) IS NULL THEN NULL ELSE
         ST_Distance(h.geom::geography,
                     ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) END AS distance_m,
       (SELECT count(*) FROM spot s WHERE s.harbour_id = h.id AND s.active) AS spot_count
FROM harbour h
WHERE (CAST(:q AS text) IS NULL OR h.name ILIKE :pattern OR similarity(h.name, :q) > 0.25)
ORDER BY
  CASE WHEN CAST(:lon AS float) IS NULL THEN NULL ELSE
    ST_Distance(h.geom::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) END
  NULLS LAST,
  CASE WHEN CAST(:q AS text) IS NULL THEN NULL ELSE similarity(h.name, :q) END DESC NULLS LAST,
  h.name
LIMIT :limit
"""

_DETAIL_SQL = """
SELECT h.id, h.slug, h.name, h.insee_code, ST_X(h.geom) AS lon, ST_Y(h.geom) AS lat,
       h.vhf_channel, h.phone, h.email, h.website, h.opening_hours, h.services,
       (SELECT count(*) FROM spot s WHERE s.harbour_id = h.id AND s.active) AS spot_count
FROM harbour h
WHERE h.slug = :slug
"""

_FIELDS_SQL = """
SELECT f.id, f.name, f.kind::text AS kind, f.capacity, f.visitor_capacity, f.operator,
       f.price_per_night_cents, f.price_note
FROM field f
WHERE f.harbour_id = :harbour_id
ORDER BY f.name NULLS LAST, f.id
"""


async def search_harbours(
    session: AsyncSession, query: str | None, near: tuple[float, float] | None, limit: int
) -> HarbourList:
    params = {
        "q": query,
        "pattern": f"%{query}%" if query else None,
        "lon": near[0] if near else None,
        "lat": near[1] if near else None,
        "limit": min(limit, 200),
    }
    rows = (await session.execute(text(_SEARCH_SQL), params)).all()
    return HarbourList(
        harbours=[
            HarbourListItem(
                id=f"harbour_{row.id}",
                slug=row.slug,
                name=row.name,
                position=[row.lon, row.lat],
                insee_code=row.insee_code,
                distance_nm=round(row.distance_m / METRES_PER_NM, 2)
                if row.distance_m is not None
                else None,
                spot_count=int(row.spot_count),
            )
            for row in rows
        ],
        attribution=attribution.REFERENTIAL,
    )


async def get_harbour(
    session: AsyncSession, slug: str, availability: AvailabilityProvider
) -> HarbourDetail:
    row = (await session.execute(text(_DETAIL_SQL), {"slug": slug})).one_or_none()
    if row is None:
        raise HarbourNotFound(f"harbour {slug!r}")
    fields = (await session.execute(text(_FIELDS_SQL), {"harbour_id": row.id})).all()
    statuses = await availability.field_status_for([int(field.id) for field in fields])
    return HarbourDetail(
        id=f"harbour_{row.id}",
        slug=row.slug,
        name=row.name,
        position=[row.lon, row.lat],
        insee_code=row.insee_code,
        vhf_channel=row.vhf_channel,
        phone=row.phone,
        email=row.email,
        website=row.website,
        opening_hours=row.opening_hours,
        services=list(row.services or []),
        fields=[
            FieldSummary(
                id=f"field_{field.id}",
                name=field.name,
                kind=SpotKind(field.kind),
                capacity=field.capacity,
                visitor_capacity=field.visitor_capacity,
                operator=field.operator,
                price_per_night_cents=field.price_per_night_cents,
                price_note=field.price_note,
                status=statuses.get(int(field.id)),
            )
            for field in fields
        ],
        spot_count=int(row.spot_count),
        attribution=attribution.REFERENTIAL,
        disclaimer=attribution.DISCLAIMER,
    )


async def harbour_id_for_slug(session: AsyncSession, slug: str) -> int:
    row = await session.execute(text("SELECT id FROM harbour WHERE slug = :slug"), {"slug": slug})
    value = row.scalar_one_or_none()
    if value is None:
        raise HarbourNotFound(f"harbour {slug!r}")
    return int(value)


async def all_slugs(session: AsyncSession) -> list[str]:
    """Feeds the build-time prerender of ~1 500 `/port/{slug}` pages (ADR-0001)."""
    rows = await session.execute(text("SELECT slug FROM harbour ORDER BY slug"))
    return [str(value) for value in rows.scalars().all()]
