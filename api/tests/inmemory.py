"""In-memory repositories, matching the production interfaces and raising the same domain
exceptions (docs/13). Repository methods are never mocked — a fake that lies teaches nothing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from datetime import datetime

from balise_api.domain.enums import ReportKind, SourceKind, SpotKind
from balise_api.domain.observation import DerivedFieldStatus, DerivedStatus, ObservationInput
from balise_api.repositories.protocols import (
    ContributorRef,
    FeedNotFound,
    FeedRef,
    FieldNotFound,
    FieldRef,
    NewObservation,
    SpotNotFound,
    SpotRef,
    StoredObservation,
)

EARTH_RADIUS_M = 6_371_000.0


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


@dataclass
class InMemorySpotRepository:
    spots: dict[int, SpotRef] = field(default_factory=dict)

    def add(self, spot: SpotRef) -> SpotRef:
        self.spots[spot.id] = spot
        return spot

    async def get(self, spot_id: int) -> SpotRef:
        spot = self.spots.get(spot_id)
        if spot is None:
            raise SpotNotFound(f"spot {spot_id}")
        return spot

    async def distance_m(self, spot_id: int, lon: float, lat: float) -> float:
        spot = await self.get(spot_id)
        return haversine_m(spot.lon, spot.lat, lon, lat)


@dataclass
class InMemoryFieldRepository:
    fields: dict[int, FieldRef] = field(default_factory=dict)
    external: dict[tuple[str, str], int] = field(default_factory=dict)

    def add(
        self, ref: FieldRef, feed_id: str | None = None, external_id: str | None = None
    ) -> FieldRef:
        self.fields[ref.id] = ref
        if feed_id and external_id:
            self.external[(feed_id, external_id)] = ref.id
        return ref

    async def get(self, field_id: int) -> FieldRef:
        ref = self.fields.get(field_id)
        if ref is None:
            raise FieldNotFound(f"field {field_id}")
        return ref

    async def get_by_external(self, feed_id: str, external_id: str) -> FieldRef:
        field_id = self.external.get((feed_id, external_id))
        if field_id is None:
            raise FieldNotFound(f"field {external_id!r} of feed {feed_id}")
        return await self.get(field_id)


@dataclass
class InMemoryObservationRepository:
    rows: list[StoredObservation] = field(default_factory=list)
    reputations: dict[int, float] = field(default_factory=dict)

    async def add(self, record: NewObservation) -> StoredObservation:
        stored = StoredObservation(id=len(self.rows) + 1, record=record)
        self.rows.append(stored)
        return stored

    async def find_by_idempotency_key(self, key: str) -> StoredObservation | None:
        return next((row for row in self.rows if row.record.idempotency_key == key), None)

    async def recent_for_spot(self, spot_id: int, since: datetime) -> list[ObservationInput]:
        return [
            self._to_input(row)
            for row in self.rows
            if row.record.spot_id == spot_id and row.record.observed_at >= since
        ]

    async def recent_for_field(self, field_id: int, since: datetime) -> list[ObservationInput]:
        return [
            self._to_input(row)
            for row in self.rows
            if row.record.field_id == field_id and row.record.observed_at >= since
        ]

    async def count_for_contributor(self, contributor_id: int, since: datetime) -> int:
        return sum(
            1
            for row in self.rows
            if row.record.contributor_id == contributor_id and row.record.observed_at >= since
        )

    def _to_input(self, row: StoredObservation) -> ObservationInput:
        record = row.record
        reputation = (
            self.reputations.get(record.contributor_id, 1.0)
            if record.contributor_id is not None
            else 1.0
        )
        return ObservationInput(
            id=row.id,
            state=record.state,
            source_kind=record.source_kind,
            report_kind=record.report_kind,
            observed_at=record.observed_at,
            confidence=record.confidence,
            source_ref=record.source_ref,
            contributor_reputation=reputation,
            free_count=record.free_count,
            contributor_id=record.contributor_id,
        )


@dataclass
class InMemoryContributorRepository:
    by_hash: dict[str, ContributorRef] = field(default_factory=dict)
    next_id: int = 1

    async def get_or_create(self, device_hash: str) -> ContributorRef:
        existing = self.by_hash.get(device_hash)
        if existing is not None:
            return existing
        ref = ContributorRef(id=self.next_id, device_hash=device_hash, reputation=1.0, banned=False)
        self.by_hash[device_hash] = ref
        self.next_id += 1
        return ref

    async def set_reputation(self, contributor_id: int, reputation: float) -> None:
        for device_hash, ref in self.by_hash.items():
            if ref.id == contributor_id:
                self.by_hash[device_hash] = replace(ref, reputation=reputation)
                return

    def reputation_of(self, contributor_id: int) -> float:
        return next(
            (ref.reputation for ref in self.by_hash.values() if ref.id == contributor_id), 1.0
        )


@dataclass
class InMemoryStatusRepository:
    spot_statuses: dict[int, DerivedStatus] = field(default_factory=dict)
    field_statuses: dict[int, DerivedFieldStatus] = field(default_factory=dict)

    async def upsert_spot(self, spot_id: int, status: DerivedStatus) -> None:
        self.spot_statuses[spot_id] = status

    async def upsert_field(self, field_id: int, status: DerivedFieldStatus) -> None:
        self.field_statuses[field_id] = status


@dataclass
class RecordingPublisher:
    published: list[tuple[SpotRef, DerivedStatus]] = field(default_factory=list)

    async def publish(self, spot: SpotRef, status: DerivedStatus) -> None:
        self.published.append((spot, status))


@dataclass
class InMemoryFeedRepository:
    feeds: dict[str, FeedRef] = field(default_factory=dict)
    tokens: dict[str, str] = field(default_factory=dict)
    spots: dict[tuple[str, str], SpotRef] = field(default_factory=dict)
    fields: dict[tuple[str, str], FieldRef] = field(default_factory=dict)
    touches: list[tuple[str, int, int]] = field(default_factory=list)

    def add(self, feed: FeedRef, token_hash: str = "hash") -> FeedRef:
        self.feeds[feed.id] = feed
        self.tokens[feed.id] = token_hash
        return feed

    async def get(self, feed_id: str) -> FeedRef:
        feed = self.feeds.get(feed_id)
        if feed is None:
            raise FeedNotFound(f"feed {feed_id}")
        return feed

    async def token_hash(self, feed_id: str) -> str:
        return self.tokens[feed_id]

    async def touch(self, feed_id: str, *, accepted: int, rejected: int, at: datetime) -> None:
        self.touches.append((feed_id, accepted, rejected))

    async def resolve_spot(self, feed: FeedRef, external_id: str) -> SpotRef:
        spot = self.spots.get((feed.id, external_id))
        if spot is None:
            raise SpotNotFound(f"spot {external_id!r} for feed {feed.id}")
        return spot

    async def resolve_field(self, feed: FeedRef, external_id: str) -> FieldRef:
        ref = self.fields.get((feed.id, external_id))
        if ref is None:
            raise FieldNotFound(f"field {external_id!r} for feed {feed.id}")
        return ref

    async def health(self, feed_id: str, now: datetime) -> dict[str, object]:
        return {"feed_id": feed_id, "stale": False}


def mooring_buoy(spot_id: int = 1, lon: float = -2.9021, lat: float = 47.5412) -> SpotRef:
    return SpotRef(id=spot_id, kind=SpotKind.MOORING_BUOY, lon=lon, lat=lat, code="B14")


def berth(spot_id: int = 2, lon: float = -2.9500, lat: float = 47.5500) -> SpotRef:
    return SpotRef(id=spot_id, kind=SpotKind.BERTH, lon=lon, lat=lat, code="A12", harbour_id=1)


def port_feed(feed_id: str = "feed.test", harbour_id: int = 1, ttl: int = 60) -> FeedRef:
    return FeedRef(
        id=feed_id,
        harbour_id=harbour_id,
        kind=SourceKind.PORT_FEED,
        trust=0.95,
        ttl_seconds=ttl,
        active=True,
    )


def community_observation(
    spot_id: int,
    state: str,
    observed_at: datetime,
    *,
    report_kind: ReportKind = ReportKind.CORRECTION,
    confidence: float = 0.55,
    contributor_id: int | None = 1,
    source_ref: str | None = "device-a",
) -> NewObservation:
    from balise_api.domain.enums import SpotState

    return NewObservation(
        state=SpotState(state),
        source_kind=SourceKind.COMMUNITY,
        report_kind=report_kind,
        observed_at=observed_at,
        confidence=confidence,
        spot_id=spot_id,
        contributor_id=contributor_id,
        source_ref=source_ref,
    )
