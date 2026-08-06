"""Community contribution rules (docs/06 T2, docs/08) with in-memory repositories."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from balise_api.domain.enums import ReportKind, SourceKind, SpotState
from balise_api.repositories.protocols import ContributorRef, RateLimited, SpotNotFound
from balise_api.services.availability.community import (
    MAX_REPORTS_PER_HOUR,
    ReportContext,
    ReportSubmission,
    clamp_observed_at,
    emission_confidence,
    submit_report,
)

from .inmemory import (
    InMemoryContributorRepository,
    InMemoryObservationRepository,
    InMemorySpotRepository,
    InMemoryStatusRepository,
    RecordingPublisher,
    mooring_buoy,
)

NOW = datetime(2026, 8, 6, 18, 0, tzinfo=UTC)


def build() -> tuple[
    ReportContext, InMemorySpotRepository, RecordingPublisher, InMemoryContributorRepository
]:
    spots = InMemorySpotRepository()
    spots.add(mooring_buoy())
    publisher = RecordingPublisher()
    contributors = InMemoryContributorRepository()
    context = ReportContext(
        spots=spots,
        observations=InMemoryObservationRepository(),
        statuses=InMemoryStatusRepository(),
        contributors=contributors,
        publisher=publisher,
    )
    return context, spots, publisher, contributors


async def contributor_of(context: ReportContext, device: str = "device-a") -> ContributorRef:
    assert context.contributors is not None
    return await context.contributors.get_or_create(device)


def test_client_clocks_are_clamped_to_a_plausible_window() -> None:
    early, clamped_early = clamp_observed_at(NOW - timedelta(hours=9), NOW)
    late, clamped_late = clamp_observed_at(NOW + timedelta(hours=2), NOW)
    kept, untouched = clamp_observed_at(NOW - timedelta(minutes=30), NOW)
    assert (clamped_early, early) == (True, NOW - timedelta(hours=6))
    assert (clamped_late, late) == (True, NOW + timedelta(minutes=5))
    assert (untouched, kept) == (False, NOW - timedelta(minutes=30))


def test_a_remote_report_is_emitted_at_half_trust() -> None:
    assert emission_confidence(ReportKind.CHECK_OUT, remote=False) == 0.55
    assert emission_confidence(ReportKind.CHECK_OUT, remote=True) == 0.28
    assert emission_confidence(ReportKind.IMPLICIT_CHECKOUT, remote=False) == 0.4


async def test_a_check_out_on_site_makes_the_spot_free_and_fans_out() -> None:
    context, _, publisher, _ = build()
    contributor = await contributor_of(context)
    outcome = await submit_report(
        context,
        ReportSubmission(
            spot_id=1,
            state=SpotState.FREE,
            observed_at=NOW,
            report_kind=ReportKind.CHECK_OUT,
            position=(-2.9021, 47.5412),
        ),
        contributor,
        NOW,
    )
    assert (outcome.remote, outcome.clamped, outcome.duplicate) == (False, False, False)
    assert (outcome.status.state, outcome.status.confidence) == (SpotState.FREE, 0.55)
    assert outcome.status.display_state is SpotState.FREE
    assert [spot.id for spot, _ in publisher.published] == [1]


async def test_a_report_from_far_away_is_kept_but_weighted_down() -> None:
    context, _, _, _ = build()
    contributor = await contributor_of(context)
    outcome = await submit_report(
        context,
        ReportSubmission(
            spot_id=1,
            state=SpotState.FREE,
            observed_at=NOW,
            report_kind=ReportKind.CHECK_OUT,
            position=(-2.8000, 47.5412),  # ~7.6 km away
        ),
        contributor,
        NOW,
    )
    assert outcome.remote is True
    # Weighted below the "never show a weak free" gate, so the map stays honest.
    assert outcome.status.display_state is SpotState.UNKNOWN


async def test_an_unknown_spot_is_rejected() -> None:
    context, _, _, _ = build()
    contributor = await contributor_of(context)
    with pytest.raises(SpotNotFound):
        await submit_report(
            context,
            ReportSubmission(spot_id=404, state=SpotState.FREE, observed_at=NOW),
            contributor,
            NOW,
        )


async def test_the_offline_queue_can_retry_without_double_counting() -> None:
    context, _, _, _ = build()
    contributor = await contributor_of(context)
    submission = ReportSubmission(
        spot_id=1,
        state=SpotState.OCCUPIED,
        observed_at=NOW,
        report_kind=ReportKind.CHECK_IN,
        idempotency_key="queued-1",
    )
    first = await submit_report(context, submission, contributor, NOW)
    second = await submit_report(context, submission, contributor, NOW)
    assert (first.duplicate, second.duplicate) == (False, True)
    assert second.observation_id == first.observation_id
    assert len(context.observations.rows) == 1  # type: ignore[attr-defined]


async def test_a_device_is_rate_limited_after_ten_reports_an_hour() -> None:
    context, _, _, _ = build()
    contributor = await contributor_of(context)
    for index in range(MAX_REPORTS_PER_HOUR):
        await submit_report(
            context,
            ReportSubmission(
                spot_id=1,
                state=SpotState.OCCUPIED,
                observed_at=NOW,
                report_kind=ReportKind.CHECK_IN,
                idempotency_key=f"key-{index}",
            ),
            contributor,
            NOW,
        )
    with pytest.raises(RateLimited):
        await submit_report(
            context,
            ReportSubmission(spot_id=1, state=SpotState.OCCUPIED, observed_at=NOW),
            contributor,
            NOW,
        )


async def test_agreement_raises_reputation_and_contradiction_lowers_it() -> None:
    context, _, _, contributors = build()
    first = await contributor_of(context, "device-a")
    second = await contributor_of(context, "device-b")
    await submit_report(
        context,
        ReportSubmission(
            spot_id=1,
            state=SpotState.OCCUPIED,
            observed_at=NOW - timedelta(minutes=10),
            report_kind=ReportKind.CHECK_IN,
        ),
        first,
        NOW,
    )
    await submit_report(
        context,
        ReportSubmission(
            spot_id=1,
            state=SpotState.OCCUPIED,
            observed_at=NOW,
            report_kind=ReportKind.CORRECTION,
        ),
        second,
        NOW,
    )
    assert contributors.reputation_of(first.id) == 1.05

    third = await contributor_of(context, "device-c")
    await submit_report(
        context,
        ReportSubmission(
            spot_id=1,
            state=SpotState.FREE,
            observed_at=NOW + timedelta(minutes=1),
            report_kind=ReportKind.CHECK_OUT,
        ),
        third,
        NOW,
    )
    assert contributors.reputation_of(second.id) == 0.8


async def test_a_stored_observation_keeps_its_audit_trail() -> None:
    context, _, _, _ = build()
    contributor = await contributor_of(context)
    await submit_report(
        context,
        ReportSubmission(
            spot_id=1,
            state=SpotState.OCCUPIED,
            observed_at=NOW - timedelta(hours=9),
            report_kind=ReportKind.CHECK_IN,
            note="3 bateaux sur coffre",
        ),
        contributor,
        NOW,
    )
    stored = context.observations.rows[0].record  # type: ignore[attr-defined]
    assert stored.source_kind is SourceKind.COMMUNITY
    assert stored.observed_at == NOW - timedelta(hours=6)  # clamped
    assert stored.payload == {"remote": False, "clamped": True, "note": "3 bateaux sur coffre"}
    assert stored.contributor_id == contributor.id
