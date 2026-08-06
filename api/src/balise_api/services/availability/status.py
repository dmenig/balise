"""Status derivation — docs/06. This module is PURE: no I/O, no clock, no ORM (ADR-0003).

    (spot_kind, observations, now) -> DerivedStatus

Everything downstream (the API, the workers, the tile invalidation) is a caller of this.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timedelta

from balise_api.domain.enums import ReportKind, SourceKind, SpotKind, SpotState
from balise_api.domain.observation import DerivedFieldStatus, DerivedStatus, ObservationInput

MINUTE = timedelta(minutes=1)
HOUR = timedelta(hours=1)

#: Base trust per tier (docs/06). Used at *emission* time to set observation.confidence;
#: derivation then works from the emitted confidence so that per-report modifiers
#: (remote report, implicit check-out) survive into the audit trail.
BASE_TRUST: dict[SourceKind, float] = {
    SourceKind.PORT_FEED: 0.95,
    SourceKind.SENSOR: 0.95,
    SourceKind.MANUAL: 0.90,
    SourceKind.COMMUNITY: 0.55,
    SourceKind.AIS: 0.50,
    SourceKind.IMPORT: 0.30,
}

#: (half-life, hard expiry) per signal. Asymmetric on purpose: "free" decays much faster
#: than "occupied" — a stale "free" costs a sailor an hour of daylight.
_DECAY: dict[tuple[SourceKind, ReportKind | None], tuple[timedelta, timedelta]] = {
    (SourceKind.PORT_FEED, None): (60 * MINUTE, 6 * HOUR),
    (SourceKind.SENSOR, None): (60 * MINUTE, 6 * HOUR),
    (SourceKind.COMMUNITY, ReportKind.CHECK_IN): (8 * HOUR, 24 * HOUR),
    (SourceKind.COMMUNITY, ReportKind.CHECK_OUT): (45 * MINUTE, 6 * HOUR),
    (SourceKind.COMMUNITY, ReportKind.IMPLICIT_CHECKOUT): (45 * MINUTE, 6 * HOUR),
    (SourceKind.COMMUNITY, ReportKind.CORRECTION): (2 * HOUR, 12 * HOUR),
    (SourceKind.COMMUNITY, None): (2 * HOUR, 12 * HOUR),
    (SourceKind.AIS, None): (20 * MINUTE, 2 * HOUR),
    (SourceKind.MANUAL, None): (24 * HOUR, 72 * HOUR),
    (SourceKind.IMPORT, None): (24 * HOUR, 72 * HOUR),
}

#: Observation window H (docs/06): short in a busy marina, long on a mooring field.
_WINDOW: dict[SpotKind, timedelta] = {
    SpotKind.BERTH: 2 * HOUR,
    SpotKind.MOORING_BUOY: 12 * HOUR,
    SpotKind.ANCHORAGE: 12 * HOUR,
    SpotKind.PILE: 12 * HOUR,
    SpotKind.QUAY: 12 * HOUR,
}

_AGREEMENT_BONUS = 1.2
#: Nominal reputation band is 0.5–1.5 (docs/06); the floor is 0 here because a shadow-weighted
#: contributor is deliberately weighted ≈ 0 by the caller (`reputation.effective_weight`).
_REPUTATION_FLOOR = 0.0
_REPUTATION_CEILING = 1.5
_MACHINE_TIER = 1


def decay_params(obs: ObservationInput) -> tuple[timedelta, timedelta]:
    key = (obs.source_kind, obs.report_kind)
    if key in _DECAY:
        return _DECAY[key]
    return _DECAY[(obs.source_kind, None)]


def observation_window(kind: SpotKind) -> timedelta:
    return _WINDOW[kind]


def score(obs: ObservationInput, now: datetime) -> float:
    """Emitted confidence × reputation × exponential decay. Zero once hard-expired."""
    half_life, hard_expiry = decay_params(obs)
    age = max(now - obs.observed_at, timedelta(0))
    if age >= hard_expiry:
        return 0.0
    reputation = 1.0
    if obs.source_kind is SourceKind.COMMUNITY:
        reputation = min(max(obs.contributor_reputation, _REPUTATION_FLOOR), _REPUTATION_CEILING)
    decay: float = 0.5 ** (age / half_life)
    return min(obs.confidence * reputation * decay, 1.0)


def _supersede_same_source(observations: list[ObservationInput]) -> list[ObservationInput]:
    """One source, one current claim: a later observation replaces its own earlier one.

    Two cases, one rule:
      * a machine reports *state*, not events — a feed that flips A12 free → occupied is certain,
        so its two readings must not compete and halve the confidence;
      * a sailor who checks in and then checks out has *left* — « je libère » must beat their own
        « j'occupe » from ten minutes ago, which is the core loop of the whole product (docs/02).

    Observations from *different* contributors stay cumulative: two sailors are two independent
    witnesses, and that is exactly what the agreement bonus rewards.
    """
    latest: dict[tuple[SourceKind, str | None], ObservationInput] = {}
    anonymous: list[ObservationInput] = []
    for obs in observations:
        if obs.tier != _MACHINE_TIER and obs.source_ref is None:
            # No identity to supersede against (an anonymised or purged observation).
            anonymous.append(obs)
            continue
        key = (obs.source_kind, obs.source_ref)
        current = latest.get(key)
        if current is None or obs.observed_at > current.observed_at:
            latest[key] = obs
    return [*anonymous, *latest.values()]


def _live(
    observations: list[ObservationInput], kind: SpotKind, now: datetime
) -> list[tuple[ObservationInput, float]]:
    window = observation_window(kind)
    in_window = [obs for obs in observations if max(now - obs.observed_at, timedelta(0)) < window]
    scored = [(obs, score(obs, now)) for obs in _supersede_same_source(in_window)]
    return [(obs, value) for obs, value in scored if value > 0.0]


def _unknown(now: datetime) -> DerivedStatus:
    return DerivedStatus(
        state=SpotState.UNKNOWN, confidence=0.0, as_of=now, source_kind=SourceKind.IMPORT
    )


def derive_status(
    kind: SpotKind, observations: list[ObservationInput], now: datetime
) -> DerivedStatus:
    live = _live(observations, kind, now)
    if not live:
        return _unknown(now)

    mass: dict[SpotState, float] = defaultdict(float)
    sources: dict[SpotState, set[SourceKind]] = defaultdict(set)
    for obs, value in live:
        mass[obs.state] += value
        sources[obs.state].add(obs.source_kind)
    bonus = {state: _AGREEMENT_BONUS if len(sources[state]) > 1 else 1.0 for state in mass}
    bonused = {state: value * bonus[state] for state, value in mass.items()}

    freshest: dict[SpotState, datetime] = {}
    for obs, _ in live:
        current = freshest.get(obs.state)
        if current is None or obs.observed_at > current:
            freshest[obs.state] = obs.observed_at
    # Equal mass is broken by recency, never alphabetically: the newer claim wins.
    winner = max(bonused, key=lambda state: (bonused[state], freshest[state]))
    total = sum(bonused.values())
    supporting = [(obs, value) for obs, value in live if obs.state is winner]
    best_obs, best_score = max(supporting, key=lambda pair: (pair[1], pair[0].observed_at))
    # The agreement bonus multiplies the *confidence*, not the ratio — inside the ratio it would
    # cancel itself out whenever nothing disagrees, which is exactly when agreement matters most.
    confidence = min(bonused[winner] / total * best_score * bonus[winner], 1.0) if total else 0.0
    status = DerivedStatus(
        state=winner,
        confidence=round(confidence, 2),
        as_of=max(obs.observed_at for obs, _ in supporting),
        source_kind=best_obs.source_kind,
        observation_id=best_obs.id,
        contributing_ids=tuple(sorted(obs.id for obs, _ in supporting if obs.id is not None)),
    )
    return _machine_authority(status, live)


def _machine_authority(
    status: DerivedStatus, live: list[tuple[ObservationInput, float]]
) -> DerivedStatus:
    """The freshest tier-1 signal has the last word about the spot it monitors.

    Two directions, one idea — the port knows its own berths:
      * it *overrides* a winner it contradicts, so two stale community "free" reports cannot
        outweigh a feed that just said "occupied" (the failure mode docs/00 says destroys trust);
      * it is a confidence *floor* for a winner it agrees with, because a sailor disagreeing does
        not make the port less sure.
    """
    machine = [(obs, value) for obs, value in live if obs.tier == _MACHINE_TIER]
    if not machine:
        return status
    best_obs, best_score = max(machine, key=lambda pair: (pair[0].observed_at, pair[1]))
    machine_confidence = round(min(best_score, 1.0), 2)
    if best_obs.state is status.state:
        if machine_confidence <= status.confidence:
            return status
        return replace(
            status,
            confidence=machine_confidence,
            as_of=max(status.as_of, best_obs.observed_at),
            source_kind=best_obs.source_kind,
            observation_id=best_obs.id,
        )
    if best_obs.observed_at <= status.as_of:
        return status
    return DerivedStatus(
        state=best_obs.state,
        confidence=machine_confidence,
        as_of=best_obs.observed_at,
        source_kind=best_obs.source_kind,
        observation_id=best_obs.id,
        contributing_ids=(best_obs.id,) if best_obs.id is not None else (),
    )


def derive_field_status(
    capacity: int | None,
    observations: list[ObservationInput],
    now: datetime,
    kind: SpotKind = SpotKind.MOORING_BUOY,
) -> DerivedFieldStatus:
    """Aggregate availability for a field we cannot enumerate (a ZMEL of 60 buoys, `num_free`)."""
    live = [
        (obs, value) for obs, value in _live(observations, kind, now) if obs.free_count is not None
    ]
    if not live:
        return DerivedFieldStatus(
            free_count=None,
            capacity=capacity,
            confidence=0.0,
            as_of=now,
            source_kind=SourceKind.IMPORT,
        )
    best_obs, best_score = max(live, key=lambda pair: (pair[0].tier * -1, pair[0].observed_at))
    free_count = max(best_obs.free_count or 0, 0)
    if capacity is not None:
        free_count = min(free_count, capacity)
    return DerivedFieldStatus(
        free_count=free_count,
        capacity=capacity,
        confidence=round(min(best_score, 1.0), 2),
        as_of=best_obs.observed_at,
        source_kind=best_obs.source_kind,
    )
