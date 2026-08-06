"""MBFS ingestion rules (docs/06 T1, ADR-0004): tolerant per line, honest on staleness."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from balise_api.domain.enums import ReportKind, SourceKind, SpotKind, SpotState
from balise_api.repositories.protocols import FieldRef
from balise_api.services.availability.feeds import (
    FeedContext,
    FeedFieldObservation,
    FeedSpotObservation,
    apply_snapshot,
    base_trust_for,
    ingest_spot_observations,
)

from .inmemory import (
    InMemoryFeedRepository,
    InMemoryObservationRepository,
    InMemorySpotRepository,
    InMemoryStatusRepository,
    RecordingPublisher,
    berth,
    port_feed,
)

NOW = datetime(2026, 8, 6, 18, 0, tzinfo=UTC)


def build() -> tuple[FeedContext, InMemoryFeedRepository, RecordingPublisher]:
    spots = InMemorySpotRepository()
    target = berth(spot_id=42)
    spots.add(target)
    feeds = InMemoryFeedRepository()
    feed = feeds.add(port_feed())
    feeds.spots[(feed.id, "A12")] = target
    feeds.fields[(feed.id, "PANNE-A")] = FieldRef(
        id=7, kind=SpotKind.BERTH, capacity=48, harbour_id=1
    )
    publisher = RecordingPublisher()
    context = FeedContext(
        feeds=feeds,
        spots=spots,
        observations=InMemoryObservationRepository(),
        statuses=InMemoryStatusRepository(),
        publisher=publisher,
    )
    return context, feeds, publisher


async def test_a_valid_line_is_accepted_and_an_unknown_one_is_rejected_alone() -> None:
    context, feeds, publisher = build()
    feed = await feeds.get("feed.test")
    result = await ingest_spot_observations(
        context,
        feed,
        [
            FeedSpotObservation(spot_id="A12", state=SpotState.FREE),
            FeedSpotObservation(spot_id="NOPE", state=SpotState.OCCUPIED),
        ],
        NOW,
    )
    assert result.accepted == 1
    assert [(item.index, item.reason) for item in result.rejected] == [(1, "unknown spot_id")]
    assert feeds.touches == [("feed.test", 1, 1)]
    assert [status.state for _, status in publisher.published] == [SpotState.FREE]


async def test_a_port_feed_reads_as_confirmed() -> None:
    context, feeds, _ = build()
    feed = await feeds.get("feed.test")
    await ingest_spot_observations(
        context, feed, [FeedSpotObservation(spot_id="A12", state=SpotState.FREE)], NOW
    )
    status = context.statuses.spot_statuses[42]  # type: ignore[attr-defined]
    assert (status.state, status.confidence, status.source_kind) == (
        SpotState.FREE,
        0.95,
        SourceKind.PORT_FEED,
    )
    assert status.display_state is SpotState.FREE


async def test_field_level_num_free_alone_is_a_valid_payload() -> None:
    """The minimum viable payload — it removes the objection capitaineries actually raise."""
    context, feeds, _ = build()
    feed = await feeds.get("feed.test")
    result = await apply_snapshot(
        context,
        feed,
        [FeedFieldObservation(field_id="PANNE-A", capacity=48, num_free=5, last_reported=NOW)],
        NOW,
    )
    assert (result.accepted, result.rejected) == (1, ())
    field_status = context.statuses.field_statuses[7]  # type: ignore[attr-defined]
    assert (field_status.free_count, field_status.capacity, field_status.confidence) == (
        5,
        48,
        0.95,
    )


async def test_a_snapshot_carries_both_levels() -> None:
    context, feeds, _ = build()
    feed = await feeds.get("feed.test")
    result = await apply_snapshot(
        context,
        feed,
        [
            FeedFieldObservation(
                field_id="PANNE-A",
                capacity=48,
                num_free=1,
                last_reported=NOW,
                spots=(FeedSpotObservation(spot_id="A12", state=SpotState.OCCUPIED),),
            )
        ],
        NOW,
    )
    assert result.accepted == 2
    assert context.statuses.spot_statuses[42].state is SpotState.OCCUPIED  # type: ignore[attr-defined]


async def test_an_unknown_field_is_rejected_without_losing_the_spots() -> None:
    context, feeds, _ = build()
    feed = await feeds.get("feed.test")
    result = await apply_snapshot(
        context,
        feed,
        [
            FeedFieldObservation(
                field_id="GHOST",
                num_free=3,
                last_reported=NOW,
                spots=(FeedSpotObservation(spot_id="A12", state=SpotState.FREE),),
            )
        ],
        NOW,
    )
    assert result.accepted == 1
    assert [item.reason for item in result.rejected] == ["unknown field_id"]
    assert context.statuses.spot_statuses[42].state is SpotState.FREE  # type: ignore[attr-defined]


async def test_a_vendor_clock_far_in_the_past_is_clamped() -> None:
    context, feeds, _ = build()
    feed = await feeds.get("feed.test")
    await ingest_spot_observations(
        context,
        feed,
        [
            FeedSpotObservation(
                spot_id="A12", state=SpotState.FREE, observed_at=NOW - timedelta(days=3)
            )
        ],
        NOW,
    )
    stored = context.observations.rows[0].record  # type: ignore[attr-defined]
    assert stored.observed_at == NOW - timedelta(hours=24)
    assert stored.report_kind is ReportKind.FEED_DELTA


def test_a_feed_cannot_declare_itself_more_trustworthy_than_its_tier() -> None:
    assert base_trust_for(SourceKind.PORT_FEED, 1.0) == 0.95
    assert base_trust_for(SourceKind.PORT_FEED, 0.6) == 0.6
