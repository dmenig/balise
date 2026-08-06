"""MBFS partner-feed ingestion (docs/06 T1, ADR-0004).

Two entry points, both tolerant by design — a rejected line never fails the batch, because a
capitainerie whose whole POST 400s stops sending.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from balise_api.domain.enums import ReportKind, SourceKind, SpotState
from balise_api.domain.observation import DerivedFieldStatus
from balise_api.repositories.protocols import (
    DomainError,
    FeedRef,
    FeedRepository,
    NewObservation,
    ObservationRepository,
    SpotRepository,
    StatusPublisher,
    StatusRepository,
)
from balise_api.services.availability.community import ReportContext, recompute_spot
from balise_api.services.availability.status import (
    BASE_TRUST,
    derive_field_status,
    observation_window,
)

FEED_CLOCK_SKEW_PAST = timedelta(hours=24)
FEED_CLOCK_SKEW_FUTURE = timedelta(minutes=5)


@dataclass(frozen=True, slots=True)
class FeedSpotObservation:
    spot_id: str
    state: SpotState
    observed_at: datetime | None = None
    until: datetime | None = None
    max_loa_m: float | None = None
    max_draft_m: float | None = None


@dataclass(frozen=True, slots=True)
class FeedFieldObservation:
    field_id: str
    num_free: int | None = None
    capacity: int | None = None
    visitor_capacity: int | None = None
    last_reported: datetime | None = None
    spots: tuple[FeedSpotObservation, ...] = ()


@dataclass(frozen=True, slots=True)
class Rejection:
    index: int
    reason: str


@dataclass(frozen=True, slots=True)
class FeedIngestResult:
    accepted: int
    rejected: tuple[Rejection, ...]


@dataclass(frozen=True, slots=True)
class FeedContext:
    feeds: FeedRepository
    spots: SpotRepository
    observations: ObservationRepository
    statuses: StatusRepository
    publisher: StatusPublisher | None = None


def _clamp(observed_at: datetime | None, now: datetime) -> datetime:
    if observed_at is None:
        return now
    return min(max(observed_at, now - FEED_CLOCK_SKEW_PAST), now + FEED_CLOCK_SKEW_FUTURE)


async def ingest_spot_observations(
    context: FeedContext,
    feed: FeedRef,
    items: list[FeedSpotObservation],
    now: datetime,
    *,
    report_kind: ReportKind = ReportKind.FEED_DELTA,
) -> FeedIngestResult:
    accepted = 0
    rejected: list[Rejection] = []
    report_context = ReportContext(
        spots=context.spots,
        observations=context.observations,
        statuses=context.statuses,
        publisher=context.publisher,
    )
    for index, item in enumerate(items):
        try:
            spot = await context.feeds.resolve_spot(feed, item.spot_id)
        except DomainError:
            rejected.append(Rejection(index=index, reason="unknown spot_id"))
            continue
        payload: dict[str, object] = {"feed_id": feed.id}
        if item.until is not None:
            payload["until"] = item.until.isoformat()
        await context.observations.add(
            NewObservation(
                state=item.state,
                source_kind=feed.kind,
                report_kind=report_kind,
                observed_at=_clamp(item.observed_at, now),
                confidence=feed.trust,
                spot_id=spot.id,
                source_ref=feed.id,
                payload=payload,
            )
        )
        await recompute_spot(report_context, spot, now)
        accepted += 1
    await context.feeds.touch(feed.id, accepted=accepted, rejected=len(rejected), at=now)
    return FeedIngestResult(accepted=accepted, rejected=tuple(rejected))


async def ingest_field_observations(
    context: FeedContext, feed: FeedRef, items: list[FeedFieldObservation], now: datetime
) -> tuple[int, list[Rejection], list[FeedSpotObservation]]:
    """Field-level `num_free` is a valid minimum MBFS payload (ADR-0004)."""
    accepted = 0
    rejected: list[Rejection] = []
    spot_items: list[FeedSpotObservation] = []
    for index, item in enumerate(items):
        spot_items.extend(item.spots)
        if item.num_free is None:
            continue
        try:
            target = await context.feeds.resolve_field(feed, item.field_id)
        except DomainError:
            rejected.append(Rejection(index=index, reason="unknown field_id"))
            continue
        capacity = item.capacity if item.capacity is not None else target.capacity
        await context.observations.add(
            NewObservation(
                state=SpotState.FREE if item.num_free > 0 else SpotState.OCCUPIED,
                source_kind=feed.kind,
                report_kind=ReportKind.FEED_SNAPSHOT,
                observed_at=_clamp(item.last_reported, now),
                confidence=feed.trust,
                field_id=target.id,
                free_count=item.num_free,
                source_ref=feed.id,
                payload={"feed_id": feed.id, "capacity": capacity},
            )
        )
        window = observation_window(target.kind)
        observations = await context.observations.recent_for_field(target.id, now - window)
        status: DerivedFieldStatus = derive_field_status(capacity, observations, now, target.kind)
        await context.statuses.upsert_field(target.id, status)
        accepted += 1
    return accepted, rejected, spot_items


async def apply_snapshot(
    context: FeedContext, feed: FeedRef, fields: list[FeedFieldObservation], now: datetime
) -> FeedIngestResult:
    field_accepted, field_rejected, spot_items = await ingest_field_observations(
        context, feed, fields, now
    )
    spot_result = await ingest_spot_observations(
        context, feed, spot_items, now, report_kind=ReportKind.FEED_SNAPSHOT
    )
    return FeedIngestResult(
        accepted=field_accepted + spot_result.accepted,
        rejected=tuple(field_rejected) + spot_result.rejected,
    )


def base_trust_for(kind: SourceKind, declared: float) -> float:
    """A feed cannot declare itself more trustworthy than its tier allows."""
    return min(declared, BASE_TRUST[kind])
