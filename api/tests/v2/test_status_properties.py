"""Property tests on the derivation (docs/13): the invariants that must never break, whatever
mixture of signals arrives."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from balise_api.domain.enums import ReportKind, SourceKind, SpotKind, SpotState
from balise_api.domain.observation import ObservationInput
from balise_api.services.availability.status import BASE_TRUST, decay_params, derive_status
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

NOW = datetime(2026, 8, 6, 18, 0, tzinfo=UTC)
STATES = [SpotState.FREE, SpotState.OCCUPIED, SpotState.RESERVED, SpotState.OUT_OF_SERVICE]
SOURCES = [
    SourceKind.PORT_FEED,
    SourceKind.SENSOR,
    SourceKind.COMMUNITY,
    SourceKind.AIS,
    SourceKind.MANUAL,
    SourceKind.IMPORT,
]
REPORT_KINDS = [
    ReportKind.CHECK_IN,
    ReportKind.CHECK_OUT,
    ReportKind.CORRECTION,
    ReportKind.IMPLICIT_CHECKOUT,
    ReportKind.FEED_DELTA,
    ReportKind.FEED_SNAPSHOT,
    ReportKind.AIS_AT_REST,
    ReportKind.IMPORT,
]

observations = st.builds(
    ObservationInput,
    state=st.sampled_from(STATES),
    source_kind=st.sampled_from(SOURCES),
    report_kind=st.sampled_from(REPORT_KINDS),
    observed_at=st.integers(min_value=0, max_value=60 * 60 * 30).map(
        lambda seconds: NOW - timedelta(seconds=seconds)
    ),
    confidence=st.floats(min_value=0.05, max_value=1.0),
    id=st.integers(min_value=1, max_value=10_000),
    source_ref=st.sampled_from(["device-a", "device-b", "feed.one", "feed.two", None]),
    contributor_reputation=st.floats(min_value=0.0, max_value=1.5),
)
kinds = st.sampled_from(list(SpotKind))
CASE = settings(max_examples=250, suppress_health_check=[HealthCheck.too_slow], deadline=None)


@CASE
@given(kind=kinds, batch=st.lists(observations, max_size=8))
def test_confidence_is_always_a_probability(kind: SpotKind, batch: list[ObservationInput]) -> None:
    status = derive_status(kind, batch, NOW)
    assert 0.0 <= status.confidence <= 1.0


@CASE
@given(kind=kinds, batch=st.lists(observations, max_size=8))
def test_as_of_is_never_in_the_future(kind: SpotKind, batch: list[ObservationInput]) -> None:
    status = derive_status(kind, batch, NOW)
    assert status.as_of <= NOW


@CASE
@given(kind=kinds, batch=st.lists(observations, min_size=1, max_size=6))
def test_an_agreeing_observation_never_lowers_confidence(
    kind: SpotKind, batch: list[ObservationInput]
) -> None:
    before = derive_status(kind, batch, NOW)
    if before.state is SpotState.UNKNOWN:
        return
    agreeing = ObservationInput(
        id=99_999,
        state=before.state,
        source_kind=SourceKind.COMMUNITY,
        report_kind=ReportKind.CORRECTION,
        observed_at=NOW,
        confidence=BASE_TRUST[SourceKind.COMMUNITY],
        source_ref="device-z",
    )
    after = derive_status(kind, [*batch, agreeing], NOW)
    assert after.state is before.state
    assert after.confidence >= before.confidence - 1e-9


@CASE
@given(kind=kinds, batch=st.lists(observations, max_size=8))
def test_a_hard_expired_state_never_wins(kind: SpotKind, batch: list[ObservationInput]) -> None:
    status = derive_status(kind, batch, NOW)
    if status.state is SpotState.UNKNOWN:
        return
    winner = next(
        obs for obs in batch if obs.state is status.state and obs.observed_at == status.as_of
    )
    _, hard_expiry = decay_params(winner)
    assert NOW - winner.observed_at < hard_expiry


@CASE
@given(
    kind=kinds,
    free_age=st.integers(min_value=0, max_value=3600),
    occupied_age=st.integers(min_value=0, max_value=3600),
    reputation=st.floats(min_value=0.0, max_value=1.5),
)
def test_free_never_beats_a_more_recent_higher_trust_occupied(
    kind: SpotKind, free_age: int, occupied_age: int, reputation: float
) -> None:
    """The failure mode that destroys trust: community "free" over a fresher port "occupied"."""
    if occupied_age >= free_age:
        return
    community_free = ObservationInput(
        id=1,
        state=SpotState.FREE,
        source_kind=SourceKind.COMMUNITY,
        report_kind=ReportKind.CHECK_OUT,
        observed_at=NOW - timedelta(seconds=free_age),
        confidence=BASE_TRUST[SourceKind.COMMUNITY],
        source_ref="device-a",
        contributor_reputation=reputation,
    )
    port_occupied = ObservationInput(
        id=2,
        state=SpotState.OCCUPIED,
        source_kind=SourceKind.PORT_FEED,
        report_kind=ReportKind.FEED_DELTA,
        observed_at=NOW - timedelta(seconds=occupied_age),
        confidence=BASE_TRUST[SourceKind.PORT_FEED],
        source_ref="feed.one",
    )
    status = derive_status(kind, [community_free, port_occupied], NOW)
    assert status.state is SpotState.OCCUPIED


@CASE
@given(kind=kinds, batch=st.lists(observations, max_size=8))
def test_display_never_shows_a_weak_free(kind: SpotKind, batch: list[ObservationInput]) -> None:
    status = derive_status(kind, batch, NOW)
    if status.display_state is SpotState.FREE:
        assert status.confidence >= 0.4
