"""Status derivation (docs/06) — test priority #1: wrong data shown confidently is the bug that
hurts in a data product."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from balise_api.domain.enums import (
    ConfidenceBucket,
    ReportKind,
    SourceKind,
    SpotKind,
    SpotState,
)
from balise_api.domain.observation import ObservationInput
from balise_api.services.availability.status import (
    BASE_TRUST,
    derive_field_status,
    derive_status,
    observation_window,
    score,
)

NOW = datetime(2026, 8, 6, 18, 0, tzinfo=UTC)


def observation(
    state: str,
    *,
    age: timedelta = timedelta(0),
    source: SourceKind = SourceKind.COMMUNITY,
    report_kind: ReportKind = ReportKind.CORRECTION,
    confidence: float | None = None,
    reputation: float = 1.0,
    source_ref: str = "device-a",
    identifier: int | None = None,
    free_count: int | None = None,
) -> ObservationInput:
    return ObservationInput(
        id=identifier,
        state=SpotState(state),
        source_kind=source,
        report_kind=report_kind,
        observed_at=NOW - age,
        confidence=BASE_TRUST[source] if confidence is None else confidence,
        source_ref=source_ref,
        contributor_reputation=reputation,
        free_count=free_count,
    )


def test_no_observation_is_unknown_not_free() -> None:
    status = derive_status(SpotKind.MOORING_BUOY, [], NOW)
    assert (status.state, status.confidence, status.display_state) == (
        SpotState.UNKNOWN,
        0.0,
        SpotState.UNKNOWN,
    )


def test_fresh_port_feed_is_confirmed() -> None:
    status = derive_status(
        SpotKind.BERTH,
        [
            observation(
                "free",
                source=SourceKind.PORT_FEED,
                report_kind=ReportKind.FEED_DELTA,
                source_ref="feed.crouesty",
                identifier=7,
            )
        ],
        NOW,
    )
    assert (status.state, status.confidence, status.source_kind, status.observation_id) == (
        SpotState.FREE,
        0.95,
        SourceKind.PORT_FEED,
        7,
    )
    assert status.bucket is ConfidenceBucket.CONFIRMED
    assert status.display_state is SpotState.FREE


def test_community_check_out_reads_as_probably_free() -> None:
    status = derive_status(
        SpotKind.MOORING_BUOY, [observation("free", report_kind=ReportKind.CHECK_OUT)], NOW
    )
    assert status.confidence == 0.55
    assert status.bucket is ConfidenceBucket.PROBABLE
    assert status.display_state is SpotState.FREE


def test_a_free_report_decays_below_the_display_threshold() -> None:
    """docs/06: a "free" check-out has a 45-minute half-life. After 90 min it must not read free."""
    status = derive_status(
        SpotKind.MOORING_BUOY,
        [observation("free", report_kind=ReportKind.CHECK_OUT, age=timedelta(minutes=90))],
        NOW,
    )
    assert status.state is SpotState.FREE
    assert status.confidence == 0.14
    assert status.display_state is SpotState.UNKNOWN


def test_occupied_survives_much_longer_than_free() -> None:
    """The asymmetry is the whole point: a stale "occupied" costs a look, a stale "free" an hour."""
    free = derive_status(
        SpotKind.MOORING_BUOY,
        [observation("free", report_kind=ReportKind.CHECK_OUT, age=timedelta(hours=3))],
        NOW,
    )
    occupied = derive_status(
        SpotKind.MOORING_BUOY,
        [observation("occupied", report_kind=ReportKind.CHECK_IN, age=timedelta(hours=3))],
        NOW,
    )
    assert free.display_state is SpotState.UNKNOWN
    assert occupied.display_state is SpotState.OCCUPIED


def test_hard_expiry_drops_an_observation_entirely() -> None:
    status = derive_status(
        SpotKind.MOORING_BUOY,
        [observation("occupied", report_kind=ReportKind.CHECK_IN, age=timedelta(hours=25))],
        NOW,
    )
    assert status.state is SpotState.UNKNOWN


def test_a_berth_uses_the_short_marina_window() -> None:
    assert observation_window(SpotKind.BERTH) == timedelta(hours=2)
    assert observation_window(SpotKind.MOORING_BUOY) == timedelta(hours=12)
    status = derive_status(
        SpotKind.BERTH,
        [observation("occupied", report_kind=ReportKind.CHECK_IN, age=timedelta(hours=3))],
        NOW,
    )
    assert status.state is SpotState.UNKNOWN


def test_two_independent_sources_agreeing_raise_confidence() -> None:
    alone = derive_status(
        SpotKind.MOORING_BUOY, [observation("occupied", report_kind=ReportKind.CHECK_IN)], NOW
    )
    together = derive_status(
        SpotKind.MOORING_BUOY,
        [
            observation("occupied", report_kind=ReportKind.CHECK_IN),
            observation(
                "occupied",
                source=SourceKind.AIS,
                report_kind=ReportKind.AIS_AT_REST,
                source_ref="mmsi-hash",
            ),
        ],
        NOW,
    )
    assert together.confidence > alone.confidence


def test_a_fresher_port_feed_vetoes_stale_community_agreement() -> None:
    """Two community "free" reports must not outweigh a port that just said "occupied"."""
    status = derive_status(
        SpotKind.BERTH,
        [
            observation(
                "free",
                report_kind=ReportKind.CHECK_OUT,
                age=timedelta(minutes=30),
                source_ref="device-a",
            ),
            observation(
                "free",
                report_kind=ReportKind.CHECK_OUT,
                age=timedelta(minutes=25),
                source_ref="device-b",
            ),
            observation(
                "occupied",
                source=SourceKind.PORT_FEED,
                report_kind=ReportKind.FEED_DELTA,
                age=timedelta(minutes=1),
                source_ref="feed.crouesty",
            ),
        ],
        NOW,
    )
    assert (status.state, status.source_kind) == (SpotState.OCCUPIED, SourceKind.PORT_FEED)
    assert status.display_state is SpotState.OCCUPIED


def test_a_sailor_leaving_supersedes_their_own_arrival() -> None:
    """« Je libère » must beat the same sailor's « j'occupe » from ten minutes ago (docs/02)."""
    status = derive_status(
        SpotKind.MOORING_BUOY,
        [
            observation(
                "occupied",
                report_kind=ReportKind.CHECK_IN,
                age=timedelta(minutes=10),
                source_ref="device-a",
            ),
            observation("free", report_kind=ReportKind.CHECK_OUT, source_ref="device-a"),
        ],
        NOW,
    )
    assert status.state is SpotState.FREE
    assert status.confidence == 0.55
    assert status.display_state is SpotState.FREE


def test_another_sailor_contradicting_lowers_confidence_to_unknown() -> None:
    status = derive_status(
        SpotKind.MOORING_BUOY,
        [
            observation("free", report_kind=ReportKind.CHECK_OUT, source_ref="device-a"),
            observation("occupied", report_kind=ReportKind.CORRECTION, source_ref="device-b"),
        ],
        NOW,
    )
    # Neither claim wins convincingly, so nothing is shown as free.
    assert status.display_state is SpotState.UNKNOWN


def test_a_feed_flipping_state_stays_certain() -> None:
    """A machine reports state, not events: its own older reading must not halve its confidence."""
    status = derive_status(
        SpotKind.BERTH,
        [
            observation(
                "free",
                source=SourceKind.PORT_FEED,
                report_kind=ReportKind.FEED_SNAPSHOT,
                age=timedelta(minutes=20),
                source_ref="feed.crouesty",
            ),
            observation(
                "occupied",
                source=SourceKind.PORT_FEED,
                report_kind=ReportKind.FEED_DELTA,
                source_ref="feed.crouesty",
            ),
        ],
        NOW,
    )
    assert (status.state, status.confidence) == (SpotState.OCCUPIED, 0.95)


def test_ais_alone_is_never_shown_as_free() -> None:
    """T3 is a hint. It may say "occupied"; it must never be the reason a pin turns green."""
    status = derive_status(
        SpotKind.MOORING_BUOY,
        [
            observation(
                "free",
                source=SourceKind.AIS,
                report_kind=ReportKind.AIS_AT_REST,
                age=timedelta(minutes=25),
                source_ref="mmsi-hash",
            )
        ],
        NOW,
    )
    assert status.display_state is SpotState.UNKNOWN


def test_shadow_weighted_contributor_cannot_move_the_state() -> None:
    status = derive_status(
        SpotKind.MOORING_BUOY,
        [observation("free", report_kind=ReportKind.CHECK_OUT, reputation=0.01)],
        NOW,
    )
    assert status.display_state is SpotState.UNKNOWN


def test_reputation_raises_a_trusted_local_report() -> None:
    trusted = derive_status(
        SpotKind.MOORING_BUOY,
        [observation("free", report_kind=ReportKind.CHECK_OUT, reputation=1.5)],
        NOW,
    )
    assert trusted.confidence > 0.55


def test_future_observations_are_not_boosted() -> None:
    ahead = observation("free", report_kind=ReportKind.CHECK_OUT, age=timedelta(minutes=-30))
    assert score(ahead, NOW) == pytest.approx(0.55)


def test_field_status_never_exceeds_capacity() -> None:
    status = derive_field_status(
        48,
        [
            observation(
                "free",
                source=SourceKind.PORT_FEED,
                report_kind=ReportKind.FEED_SNAPSHOT,
                source_ref="feed.crouesty",
                free_count=60,
            )
        ],
        NOW,
    )
    assert (status.free_count, status.capacity, status.confidence) == (48, 48, 0.95)


def test_field_status_without_a_count_is_unknown() -> None:
    status = derive_field_status(48, [], NOW)
    assert (status.free_count, status.confidence) == (None, 0.0)
