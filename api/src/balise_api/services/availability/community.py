"""Community contribution path (docs/06 T2, docs/08 `POST /reports`).

Depends on repository protocols only, so the whole rule set is unit-testable with the in-memory
repositories — no database, no HTTP.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from balise_api.domain.enums import ReportKind, SourceKind, SpotState
from balise_api.domain.observation import DerivedStatus
from balise_api.repositories.protocols import (
    ContributorRef,
    ContributorRepository,
    NewObservation,
    ObservationRepository,
    RateLimited,
    SpotRef,
    SpotRepository,
    StatusPublisher,
    StatusRepository,
)
from balise_api.services.availability import reputation as reputation_rules
from balise_api.services.availability.status import (
    BASE_TRUST,
    derive_status,
    observation_window,
)

CLOCK_SKEW_PAST = timedelta(hours=6)
CLOCK_SKEW_FUTURE = timedelta(minutes=5)
PLAUSIBILITY_RADIUS_M = 500.0
MAX_REPORTS_PER_HOUR = 10
IMPLICIT_CHECKOUT_CONFIDENCE = 0.4


@dataclass(frozen=True, slots=True)
class ReportSubmission:
    spot_id: int
    state: SpotState
    observed_at: datetime
    report_kind: ReportKind = ReportKind.CORRECTION
    position: tuple[float, float] | None = None
    note: str | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True, slots=True)
class ReportOutcome:
    observation_id: int
    status: DerivedStatus
    clamped: bool
    remote: bool
    duplicate: bool = False


@dataclass(frozen=True, slots=True)
class ReportContext:
    spots: SpotRepository
    observations: ObservationRepository
    statuses: StatusRepository
    #: Absent on the partner-feed path: a port has no reputation to earn.
    contributors: ContributorRepository | None = None
    publisher: StatusPublisher | None = None


def clamp_observed_at(observed_at: datetime, now: datetime) -> tuple[datetime, bool]:
    floor, ceiling = now - CLOCK_SKEW_PAST, now + CLOCK_SKEW_FUTURE
    if observed_at < floor:
        return floor, True
    if observed_at > ceiling:
        return ceiling, True
    return observed_at, False


def emission_confidence(report_kind: ReportKind, *, remote: bool) -> float:
    base = (
        IMPLICIT_CHECKOUT_CONFIDENCE
        if report_kind is ReportKind.IMPLICIT_CHECKOUT
        else BASE_TRUST[SourceKind.COMMUNITY]
    )
    return round(base / 2 if remote else base, 2)


async def submit_report(
    context: ReportContext,
    submission: ReportSubmission,
    contributor: ContributorRef,
    now: datetime,
) -> ReportOutcome:
    if submission.idempotency_key:
        existing = await context.observations.find_by_idempotency_key(submission.idempotency_key)
        if existing is not None:
            spot = await context.spots.get(submission.spot_id)
            status = await recompute_spot(context, spot, now)
            return ReportOutcome(
                observation_id=existing.id,
                status=status,
                clamped=False,
                remote=False,
                duplicate=True,
            )

    recent = await context.observations.count_for_contributor(
        contributor.id, now - timedelta(hours=1)
    )
    if recent >= MAX_REPORTS_PER_HOUR:
        raise RateLimited(f"{recent} signalements dans la dernière heure")

    spot = await context.spots.get(submission.spot_id)
    observed_at, clamped = clamp_observed_at(submission.observed_at, now)
    remote = False
    if submission.position is not None:
        distance = await context.spots.distance_m(spot.id, *submission.position)
        remote = distance > PLAUSIBILITY_RADIUS_M

    payload: dict[str, object] = {"remote": remote}
    if clamped:
        payload["clamped"] = True
    if submission.note:
        payload["note"] = submission.note[:280]

    stored = await context.observations.add(
        NewObservation(
            state=submission.state,
            source_kind=SourceKind.COMMUNITY,
            report_kind=submission.report_kind,
            observed_at=observed_at,
            confidence=emission_confidence(submission.report_kind, remote=remote),
            spot_id=spot.id,
            source_ref=contributor.device_hash,
            contributor_id=contributor.id,
            idempotency_key=submission.idempotency_key,
            payload=payload,
        )
    )
    status = await recompute_spot(context, spot, now)
    await _settle_reputations(context, spot, now)
    return ReportOutcome(observation_id=stored.id, status=status, clamped=clamped, remote=remote)


async def recompute_spot(context: ReportContext, spot: SpotRef, now: datetime) -> DerivedStatus:
    window = observation_window(spot.kind)
    observations = await context.observations.recent_for_spot(spot.id, now - window)
    weighted = [
        replace(
            obs,
            contributor_reputation=reputation_rules.effective_weight(obs.contributor_reputation),
        )
        for obs in observations
    ]
    status = derive_status(spot.kind, weighted, now)
    await context.statuses.upsert_spot(spot.id, status)
    if context.publisher is not None:
        await context.publisher.publish(spot, status)
    return status


async def _settle_reputations(context: ReportContext, spot: SpotRef, now: datetime) -> None:
    """Agreement/contradiction feedback (docs/06 T2): +0.05 confirmed, −0.2 contradicted."""
    if context.contributors is None:
        return
    window = observation_window(spot.kind)
    observations = sorted(
        await context.observations.recent_for_spot(spot.id, now - window),
        key=lambda obs: obs.observed_at,
    )
    if len(observations) < 2:
        return
    latest = observations[-1]
    for previous in observations[:-1]:
        if previous.contributor_id is None or previous.contributor_id == latest.contributor_id:
            continue
        verdict = reputation_rules.judge(previous, latest)
        if verdict is None:
            continue
        await context.contributors.set_reputation(
            previous.contributor_id,
            reputation_rules.apply_outcome(previous.contributor_reputation, agreed=verdict),
        )
