from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from balise_api.domain.enums import ReportKind, SpotKind
from balise_api.domain.observation import DerivedFieldStatus, DerivedStatus, ObservationInput
from balise_api.models import Contributor, Field, FieldStatus, Observation, Spot, SpotStatus
from balise_api.repositories.protocols import (
    ContributorRef,
    FieldNotFound,
    FieldRef,
    NewObservation,
    SpotNotFound,
    SpotRef,
    StoredObservation,
)


def _report_kind(payload: dict[str, object]) -> ReportKind:
    raw = payload.get("report_kind")
    return ReportKind(raw) if isinstance(raw, str) else ReportKind.IMPORT


def _to_input(row: Observation, reputation: float) -> ObservationInput:
    return ObservationInput(
        id=row.id,
        state=row.state,
        source_kind=row.source_kind,
        report_kind=_report_kind(row.payload),
        observed_at=row.observed_at,
        confidence=float(row.confidence),
        source_ref=row.source_ref,
        contributor_reputation=reputation,
        free_count=row.free_count,
        contributor_id=row.contributor_id,
    )


class SqlSpotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, spot_id: int) -> SpotRef:
        stmt = select(
            Spot.id,
            Spot.kind,
            func.ST_X(Spot.geom).label("lon"),
            func.ST_Y(Spot.geom).label("lat"),
            Spot.field_id,
            Spot.harbour_id,
            Spot.code,
        ).where(Spot.id == spot_id, Spot.active)
        row = (await self._session.execute(stmt)).one_or_none()
        if row is None:
            raise SpotNotFound(f"spot {spot_id}")
        return SpotRef(
            id=row.id,
            kind=SpotKind(row.kind),
            lon=float(row.lon),
            lat=float(row.lat),
            field_id=row.field_id,
            harbour_id=row.harbour_id,
            code=row.code,
        )

    async def distance_m(self, spot_id: int, lon: float, lat: float) -> float:
        """Metres on the spheroid. Raw SQL: the `::geography` casts belong to the columns, and
        binding them through the ORM leaves psycopg unable to infer the parameter types."""
        result = await self._session.execute(
            text(
                """
                SELECT ST_Distance(
                         s.geom::geography,
                         ST_SetSRID(ST_MakePoint(CAST(:lon AS float8), CAST(:lat AS float8)),
                                    4326)::geography
                       ) AS distance_m
                FROM spot s WHERE s.id = :spot_id
                """
            ),
            {"spot_id": spot_id, "lon": lon, "lat": lat},
        )
        value = result.scalar_one_or_none()
        if value is None:
            raise SpotNotFound(f"spot {spot_id}")
        return float(value)


class SqlFieldRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, field_id: int) -> FieldRef:
        stmt = select(Field.id, Field.kind, Field.capacity, Field.harbour_id).where(
            Field.id == field_id
        )
        row = (await self._session.execute(stmt)).one_or_none()
        if row is None:
            raise FieldNotFound(f"field {field_id}")
        return FieldRef(
            id=row.id, kind=SpotKind(row.kind), capacity=row.capacity, harbour_id=row.harbour_id
        )

    async def get_by_external(self, feed_id: str, external_id: str) -> FieldRef:
        stmt = select(Field.id, Field.kind, Field.capacity, Field.harbour_id).where(
            Field.external_ids[feed_id].astext == external_id
        )
        row = (await self._session.execute(stmt)).one_or_none()
        if row is None:
            raise FieldNotFound(f"field {external_id!r} of feed {feed_id}")
        return FieldRef(
            id=row.id, kind=SpotKind(row.kind), capacity=row.capacity, harbour_id=row.harbour_id
        )


class SqlObservationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, record: NewObservation) -> StoredObservation:
        row = Observation(
            spot_id=record.spot_id,
            field_id=record.field_id,
            state=record.state,
            free_count=record.free_count,
            source_kind=record.source_kind,
            source_ref=record.source_ref,
            contributor_id=record.contributor_id,
            observed_at=record.observed_at,
            confidence=Decimal(str(round(record.confidence, 2))),
            payload={**record.payload, "report_kind": record.report_kind.value},
            idempotency_key=record.idempotency_key,
        )
        self._session.add(row)
        await self._session.flush()
        return StoredObservation(id=row.id, record=record)

    async def find_by_idempotency_key(self, key: str) -> StoredObservation | None:
        stmt = select(Observation).where(Observation.idempotency_key == key)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return StoredObservation(
            id=row.id,
            record=NewObservation(
                state=row.state,
                source_kind=row.source_kind,
                report_kind=_report_kind(row.payload),
                observed_at=row.observed_at,
                confidence=float(row.confidence),
                spot_id=row.spot_id,
                field_id=row.field_id,
                free_count=row.free_count,
                source_ref=row.source_ref,
                contributor_id=row.contributor_id,
                idempotency_key=row.idempotency_key,
                payload=row.payload,
            ),
        )

    async def _recent(self, column: object, target: int, since: datetime) -> list[ObservationInput]:
        stmt = (
            select(Observation, Contributor.reputation)
            .outerjoin(Contributor, Observation.contributor_id == Contributor.id)
            .where(
                column == target,  # type: ignore[arg-type]
                Observation.observed_at >= since,
                Observation.suppressed.is_(False),
            )
            .order_by(Observation.observed_at.desc())
            .limit(500)
        )
        rows = (await self._session.execute(stmt)).all()
        return [_to_input(obs, float(rep) if rep is not None else 1.0) for obs, rep in rows]

    async def recent_for_spot(self, spot_id: int, since: datetime) -> list[ObservationInput]:
        return await self._recent(Observation.spot_id, spot_id, since)

    async def recent_for_field(self, field_id: int, since: datetime) -> list[ObservationInput]:
        return await self._recent(Observation.field_id, field_id, since)

    async def count_for_contributor(self, contributor_id: int, since: datetime) -> int:
        stmt = select(func.count()).where(
            Observation.contributor_id == contributor_id, Observation.received_at >= since
        )
        return int((await self._session.execute(stmt)).scalar_one())


class SqlContributorRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(self, device_hash: str) -> ContributorRef:
        stmt = (
            insert(Contributor)
            .values(device_hash=device_hash)
            .on_conflict_do_nothing(index_elements=[Contributor.device_hash])
            .returning(Contributor.id, Contributor.reputation, Contributor.banned)
        )
        row = (await self._session.execute(stmt)).one_or_none()
        if row is None:
            existing = select(Contributor.id, Contributor.reputation, Contributor.banned).where(
                Contributor.device_hash == device_hash
            )
            row = (await self._session.execute(existing)).one()
        return ContributorRef(
            id=row.id,
            device_hash=device_hash,
            reputation=float(row.reputation),
            banned=bool(row.banned),
        )

    async def set_reputation(self, contributor_id: int, reputation: float) -> None:
        row = await self._session.get(Contributor, contributor_id)
        if row is not None:
            row.reputation = Decimal(str(round(reputation, 2)))


class SqlStatusRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_spot(self, spot_id: int, status: DerivedStatus) -> None:
        values = {
            "spot_id": spot_id,
            "state": status.state,
            "confidence": Decimal(str(round(status.confidence, 2))),
            "as_of": status.as_of,
            "source_kind": status.source_kind,
            "observation_id": status.observation_id,
            "updated_at": func.now(),
        }
        stmt = insert(SpotStatus).values(values)
        await self._session.execute(
            stmt.on_conflict_do_update(
                index_elements=[SpotStatus.spot_id],
                set_={key: value for key, value in values.items() if key != "spot_id"},
            )
        )

    async def upsert_field(self, field_id: int, status: DerivedFieldStatus) -> None:
        values = {
            "field_id": field_id,
            "free_count": status.free_count,
            "capacity": status.capacity,
            "confidence": Decimal(str(round(status.confidence, 2))),
            "as_of": status.as_of,
            "source_kind": status.source_kind,
            "updated_at": func.now(),
        }
        stmt = insert(FieldStatus).values(values)
        await self._session.execute(
            stmt.on_conflict_do_update(
                index_elements=[FieldStatus.field_id],
                set_={key: value for key, value in values.items() if key != "field_id"},
            )
        )
