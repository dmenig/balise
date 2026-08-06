"""S2 — the domain seam (docs/06 §A).

One port, two implementations. v1 wires the null one, v2 wires the SQL one, and **that wiring is the
only place in the codebase that knows availability exists** (docs/11: one reference to the flag).

A missing status is an ordinary empty-dict case, never a special case: the read path calls the
provider and always serialises whatever comes back, so the seam is load-bearing from day one and
cannot silently rot.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from balise_api.domain.enums import ConfidenceBucket, SourceKind, SpotState
from balise_api.queries.display import DISPLAY_CONFIDENCE_SQL, DISPLAY_STATE_SQL
from balise_api.schemas.common import FieldStatusOut, StatusOut
from balise_api.schemas.spots import ObservationTrace


class AvailabilityProvider(Protocol):
    """Reads availability for a page of spots/fields. Never writes, never raises on absence."""

    async def status_for(self, spot_ids: list[int]) -> dict[int, StatusOut]: ...

    async def field_status_for(self, field_ids: list[int]) -> dict[int, FieldStatusOut]: ...

    async def observations_for(self, spot_id: int) -> list[ObservationTrace]: ...


class NullAvailabilityProvider:
    """v1. There is no availability, so there is nothing to return — and nothing to explain.

    Takes the session it will not use, so that both providers share one factory signature and the
    wiring in `main.py` is a single assignment either way.
    """

    def __init__(self, session: AsyncSession | None = None) -> None:
        self._session = session

    async def status_for(self, spot_ids: list[int]) -> dict[int, StatusOut]:
        return {}

    async def field_status_for(self, field_ids: list[int]) -> dict[int, FieldStatusOut]:
        return {}

    async def observations_for(self, spot_id: int) -> list[ObservationTrace]:
        return []


_SPOT_STATUS_SQL = f"""
SELECT st.spot_id,
       ({DISPLAY_STATE_SQL}) AS display_state,
       ({DISPLAY_CONFIDENCE_SQL}) AS display_confidence,
       st.as_of, st.source_kind::text AS source_kind
FROM spot_status st
WHERE st.spot_id = ANY(:spot_ids)
"""

_OBSERVATIONS_SQL = """
SELECT source_kind::text AS source_kind, state::text AS state, observed_at, confidence
FROM observation
WHERE spot_id = :spot_id AND NOT suppressed
ORDER BY observed_at DESC
LIMIT 5
"""

_FIELD_STATUS_SQL = """
SELECT fs.field_id, fs.free_count, fs.capacity, fs.confidence, fs.as_of,
       fs.source_kind::text AS source_kind
FROM field_status fs
WHERE fs.field_id = ANY(:field_ids)
"""

_BUCKETS = (
    (0.8, ConfidenceBucket.CONFIRMED),
    (0.5, ConfidenceBucket.PROBABLE),
    (0.3, ConfidenceBucket.UNCERTAIN),
)


def _bucket(confidence: float) -> ConfidenceBucket:
    for threshold, bucket in _BUCKETS:
        if confidence >= threshold:
            return bucket
    return ConfidenceBucket.UNKNOWN


class SqlAvailabilityProvider:
    """v2. Reads the `spot_status` projection and applies the display gate (docs/06 §B.6).

    Swapping this in for the null one is the whole of the M3 wiring — and, if the ground-truth audit
    comes back under 85 %, swapping it back out is the whole of the rollback (docs/14 M3).
    """

    def __init__(self, session: AsyncSession, now: datetime | None = None) -> None:
        self._session = session
        self._now = now or datetime.now(UTC)

    async def status_for(self, spot_ids: list[int]) -> dict[int, StatusOut]:
        if not spot_ids:
            return {}
        rows = (await self._session.execute(text(_SPOT_STATUS_SQL), {"spot_ids": spot_ids})).all()
        out: dict[int, StatusOut] = {}
        for row in rows:
            state = SpotState(row.display_state)
            if state is SpotState.UNKNOWN or row.as_of is None:
                continue  # unknown is the absence of a status, not a status
            confidence = float(row.display_confidence)
            out[int(row.spot_id)] = StatusOut(
                state=state,
                confidence=confidence,
                bucket=_bucket(confidence),
                as_of=row.as_of,
                source_kind=SourceKind(row.source_kind),
                age_seconds=max(int((self._now - row.as_of).total_seconds()), 0),
            )
        return out

    async def field_status_for(self, field_ids: list[int]) -> dict[int, FieldStatusOut]:
        if not field_ids:
            return {}
        rows = (
            await self._session.execute(text(_FIELD_STATUS_SQL), {"field_ids": field_ids})
        ).all()
        return {
            int(row.field_id): FieldStatusOut(
                free=row.free_count,
                capacity=row.capacity,
                confidence=float(row.confidence),
                as_of=row.as_of,
                source_kind=SourceKind(row.source_kind),
            )
            for row in rows
        }

    async def observations_for(self, spot_id: int) -> list[ObservationTrace]:
        """The audit trail a sailor may see: source kind and age only, never who (docs/04 §4)."""
        rows = (await self._session.execute(text(_OBSERVATIONS_SQL), {"spot_id": spot_id})).all()
        return [
            ObservationTrace(
                source_kind=SourceKind(row.source_kind),
                state=SpotState(row.state),
                age_seconds=max(int((self._now - row.observed_at).total_seconds()), 0),
                confidence=float(row.confidence),
            )
            for row in rows
        ]
