"""The v1 read path (docs/07): geometry and static attributes from PostGIS, availability from the
provider seam — on every request, so the seam is load-bearing and cannot silently break."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from balise_api import attribution
from balise_api.domain.enums import SpotKind
from balise_api.repositories.protocols import SpotNotFound
from balise_api.schemas.common import BboxValue, Feature, FeatureCollection, Geometry, StatusOut
from balise_api.schemas.spots import FieldSummary, HarbourSummary, SpotDetail, SpotProperties
from balise_api.services.availability import AvailabilityProvider

MAX_LIMIT = 500
SortKey = Literal["distance", "price"]

#: Wind sectors a spot can be exposed to. "Sheltered from NW" means NW is not in `exposure`.
SECTORS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


@dataclass(frozen=True, slots=True)
class SpotFilters:
    bbox: BboxValue
    kinds: tuple[SpotKind, ...] = ()
    max_draft_m: float | None = None
    max_loa_m: float | None = None
    visitor: bool | None = None
    sheltered_from: tuple[str, ...] = ()
    sort: SortKey = "distance"
    limit: int = 50
    cursor: int | None = None


#: The `LEFT JOIN spot_status` is deliberate in v1 (docs/06 §A/S1): the query shape, the indexes and
#: the cascades are settled and exercised from day one. It always yields NULL until v2.
_LIST_SQL = """
SELECT s.id, ST_X(s.geom) AS lon, ST_Y(s.geom) AS lat, s.kind::text AS kind, s.code,
       s.harbour_id, s.field_id, s.visitor, s.depth_m, s.max_loa_m, s.max_draft_m, s.max_beam_m,
       s.holding, s.exposure, h.name AS harbour_name, f.price_per_night_cents,
       st.spot_id AS has_status
FROM spot s
LEFT JOIN spot_status st ON st.spot_id = s.id
LEFT JOIN harbour h ON h.id = s.harbour_id
LEFT JOIN field f ON f.id = s.field_id
WHERE s.active
  AND s.geom && ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326)
  AND (CAST(:kinds AS text[]) IS NULL OR s.kind::text = ANY(:kinds))
  AND (CAST(:visitor AS boolean) IS NULL OR s.visitor = :visitor)
  AND (CAST(:draft AS numeric) IS NULL
       OR COALESCE(s.max_draft_m, s.depth_m) IS NULL
       OR COALESCE(s.max_draft_m, s.depth_m) >= :draft)
  AND (CAST(:loa AS numeric) IS NULL OR s.max_loa_m IS NULL OR s.max_loa_m >= :loa)
  AND (CAST(:sheltered AS text[]) IS NULL OR NOT (s.exposure && CAST(:sheltered AS text[])))
  AND (CAST(:cursor AS bigint) IS NULL OR s.id > :cursor)
ORDER BY
  CASE WHEN :sort = 'price' THEN COALESCE(f.price_per_night_cents, 2147483647) END NULLS LAST,
  s.geom <-> ST_SetSRID(ST_MakePoint(:centre_lon, :centre_lat), 4326),
  s.id
LIMIT :limit
"""

_DETAIL_SQL = """
SELECT s.id, ST_X(s.geom) AS lon, ST_Y(s.geom) AS lat, s.kind::text AS kind, s.code, s.visitor,
       s.depth_m, s.max_loa_m, s.max_draft_m, s.max_beam_m, s.holding, s.exposure,
       s.harbour_id, s.field_id,
       f.name AS field_name, f.kind::text AS field_kind, f.capacity, f.visitor_capacity,
       f.operator, f.price_per_night_cents, f.price_note,
       h.slug, h.name AS harbour_name, h.vhf_channel, h.phone, h.website, h.opening_hours,
       h.services,
       st.spot_id AS has_status
FROM spot s
LEFT JOIN spot_status st ON st.spot_id = s.id
LEFT JOIN field f ON f.id = s.field_id
LEFT JOIN harbour h ON h.id = s.harbour_id
WHERE s.id = :spot_id AND s.active
"""


def _float(value: Any) -> float | None:
    return float(value) if value is not None else None


def _properties(
    row: Any, status: StatusOut | None, harbour_id: str | None, field_id: str | None
) -> SpotProperties:
    return SpotProperties(
        kind=SpotKind(row.kind),
        code=row.code,
        harbour_id=harbour_id,
        harbour_name=getattr(row, "harbour_name", None),
        field_id=field_id,
        visitor=row.visitor,
        depth_m=_float(row.depth_m),
        max_loa_m=_float(row.max_loa_m),
        max_draft_m=_float(row.max_draft_m),
        max_beam_m=_float(row.max_beam_m),
        holding=row.holding,
        exposure=list(row.exposure or []),
        price_per_night_cents=row.price_per_night_cents,
        status=status,
    )


async def list_spots(
    session: AsyncSession, filters: SpotFilters, availability: AvailabilityProvider
) -> FeatureCollection:
    params: dict[str, Any] = {
        "min_lon": filters.bbox.min_lon,
        "min_lat": filters.bbox.min_lat,
        "max_lon": filters.bbox.max_lon,
        "max_lat": filters.bbox.max_lat,
        "centre_lon": (filters.bbox.min_lon + filters.bbox.max_lon) / 2,
        "centre_lat": (filters.bbox.min_lat + filters.bbox.max_lat) / 2,
        "kinds": [kind.value for kind in filters.kinds] or None,
        "visitor": filters.visitor,
        "draft": filters.max_draft_m,
        "loa": filters.max_loa_m,
        "sheltered": list(filters.sheltered_from) or None,
        "sort": filters.sort,
        "cursor": filters.cursor,
        "limit": min(filters.limit, MAX_LIMIT),
    }
    rows = (await session.execute(text(_LIST_SQL), params)).all()
    statuses = await availability.status_for([int(row.id) for row in rows])
    features = [
        Feature(
            id=f"spot_{row.id}",
            geometry=Geometry(type="Point", coordinates=[row.lon, row.lat]),
            properties=_properties(
                row,
                statuses.get(int(row.id)),
                f"harbour_{row.harbour_id}" if row.harbour_id else None,
                f"field_{row.field_id}" if row.field_id else None,
            ).model_dump(mode="json"),
        )
        for row in rows
    ]
    return FeatureCollection(
        features=features,
        attribution=attribution.REFERENTIAL,
        next_cursor=str(rows[-1].id) if len(rows) == params["limit"] else None,
        disclaimer=attribution.DISCLAIMER,
    )


async def get_spot(
    session: AsyncSession, spot_id: int, availability: AvailabilityProvider
) -> SpotDetail:
    row = (await session.execute(text(_DETAIL_SQL), {"spot_id": spot_id})).one_or_none()
    if row is None:
        raise SpotNotFound(f"spot {spot_id}")
    kind = SpotKind(row.kind)
    statuses = await availability.status_for([spot_id])
    field_statuses = await availability.field_status_for(
        [int(row.field_id)] if row.field_id else []
    )

    observations = await availability.observations_for(spot_id)

    status = statuses.get(spot_id)
    warnings = [attribution.DEPTH_WARNING]
    if kind is SpotKind.MOORING_BUOY:
        warnings.insert(
            0,
            attribution.MOORING_STATUS_WARNING if status else attribution.MOORING_WARNING,
        )

    harbour_id = f"harbour_{row.harbour_id}" if row.harbour_id is not None else None
    field_id = f"field_{row.field_id}" if row.field_id is not None else None
    return SpotDetail(
        id=f"spot_{row.id}",
        kind=kind,
        code=row.code,
        position=[row.lon, row.lat],
        properties=_properties(row, status, harbour_id, field_id),
        field=FieldSummary(
            id=field_id,
            name=row.field_name,
            kind=SpotKind(row.field_kind),
            capacity=row.capacity,
            visitor_capacity=row.visitor_capacity,
            operator=row.operator,
            price_per_night_cents=row.price_per_night_cents,
            price_note=row.price_note,
            status=field_statuses.get(int(row.field_id)),
        )
        if field_id is not None
        else None,
        harbour=HarbourSummary(
            id=harbour_id,
            slug=row.slug,
            name=row.harbour_name,
            vhf_channel=row.vhf_channel,
            phone=row.phone,
            website=row.website,
            opening_hours=row.opening_hours,
            services=list(row.services or []),
        )
        if harbour_id is not None
        else None,
        observations=observations,
        warnings=warnings,
        attribution=attribution.REFERENTIAL,
        disclaimer=attribution.DISCLAIMER,
    )
