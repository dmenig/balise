"""v2 — the volatile companion to cached tiles (`GET /status`, docs/08).

Kept out of the v1 read path entirely: in v1 the endpoint returns 501 and nothing calls this.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from balise_api.domain.enums import SourceKind, SpotState
from balise_api.queries.display import DISPLAY_CONFIDENCE_SQL, DISPLAY_STATE_SQL
from balise_api.schemas.common import BboxValue
from balise_api.schemas.spots import StatusMap, StatusMapEntry

_SPOTS_SQL = f"""
SELECT s.id, ({DISPLAY_STATE_SQL}) AS display_state,
       ({DISPLAY_CONFIDENCE_SQL}) AS display_confidence, st.as_of,
       st.source_kind::text AS source_kind
FROM spot_status st
JOIN spot s ON s.id = st.spot_id
WHERE s.active
  AND s.geom && ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326)
  AND (CAST(:since AS timestamptz) IS NULL OR st.updated_at > :since)
LIMIT 20000
"""

_FIELDS_SQL = """
SELECT fs.field_id, fs.free_count, fs.capacity, fs.confidence
FROM field_status fs
JOIN field f ON f.id = fs.field_id
LEFT JOIN harbour h ON h.id = f.harbour_id
WHERE COALESCE(f.area, h.geom) && ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326)
  AND (CAST(:since AS timestamptz) IS NULL OR fs.updated_at > :since)
LIMIT 5000
"""


async def status_map(
    session: AsyncSession, bbox: BboxValue, since: datetime | None, now: datetime
) -> StatusMap:
    params = {
        "min_lon": bbox.min_lon,
        "min_lat": bbox.min_lat,
        "max_lon": bbox.max_lon,
        "max_lat": bbox.max_lat,
        "since": since,
    }
    spot_rows = (await session.execute(text(_SPOTS_SQL), params)).all()
    field_rows = (await session.execute(text(_FIELDS_SQL), params)).all()
    return StatusMap(
        as_of=now.astimezone(UTC),
        spots={
            str(row.id): (
                SpotState(row.display_state),
                float(row.display_confidence),
                row.as_of,
                SourceKind(row.source_kind),
            )
            for row in spot_rows
        },
        fields={
            str(row.field_id): StatusMapEntry(
                free=row.free_count, capacity=row.capacity, confidence=float(row.confidence)
            )
            for row in field_rows
        },
    )
