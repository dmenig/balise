from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from balise_api.domain.enums import (
    TIER_BY_SOURCE,
    ConfidenceBucket,
    ReportKind,
    SourceKind,
    SpotState,
)


@dataclass(frozen=True, slots=True)
class ObservationInput:
    """One raw signal about one spot (or field) at one instant. Immutable by design (ADR-0003)."""

    state: SpotState
    source_kind: SourceKind
    report_kind: ReportKind
    observed_at: datetime
    confidence: float
    id: int | None = None
    source_ref: str | None = None
    contributor_reputation: float = 1.0
    free_count: int | None = None
    #: Internal id, read by the reputation loop only — never by `derive_status`, never served.
    contributor_id: int | None = None

    @property
    def tier(self) -> int:
        return TIER_BY_SOURCE[self.source_kind]


@dataclass(frozen=True, slots=True)
class DerivedStatus:
    """The derived state of one spot. `state` is what we know, `display_state` is what we show."""

    state: SpotState
    confidence: float
    as_of: datetime
    source_kind: SourceKind
    observation_id: int | None = None
    contributing_ids: tuple[int, ...] = field(default_factory=tuple)

    @property
    def bucket(self) -> ConfidenceBucket:
        if self.confidence >= 0.8:
            return ConfidenceBucket.CONFIRMED
        if self.confidence >= 0.5:
            return ConfidenceBucket.PROBABLE
        if self.confidence >= 0.3:
            return ConfidenceBucket.UNCERTAIN
        return ConfidenceBucket.UNKNOWN

    @property
    def display_state(self) -> SpotState:
        """Honesty gate (docs/06): anything ambiguous collapses to `unknown`.

        A `free` below 0.4 is never shown as free (invariant 3 of docs/05).
        """
        if self.bucket is ConfidenceBucket.UNKNOWN:
            return SpotState.UNKNOWN
        if self.state is SpotState.FREE and self.confidence < 0.4:
            return SpotState.UNKNOWN
        return self.state


@dataclass(frozen=True, slots=True)
class DerivedFieldStatus:
    free_count: int | None
    capacity: int | None
    confidence: float
    as_of: datetime
    source_kind: SourceKind
