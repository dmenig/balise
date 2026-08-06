"""Contributor reputation (docs/06 T2). Pure functions, no I/O."""

from __future__ import annotations

from balise_api.domain.enums import SourceKind, SpotState
from balise_api.domain.observation import ObservationInput

REPUTATION_FLOOR = 0.2
REPUTATION_CEILING = 1.5
AGREEMENT_DELTA = 0.05
CONTRADICTION_DELTA = -0.2
SHADOW_WEIGHT_THRESHOLD = 0.4


def apply_outcome(reputation: float, *, agreed: bool) -> float:
    delta = AGREEMENT_DELTA if agreed else CONTRADICTION_DELTA
    return round(min(max(reputation + delta, REPUTATION_FLOOR), REPUTATION_CEILING), 2)


def effective_weight(reputation: float) -> float:
    """Below the threshold a contributor is shadow-weighted: accepted, weighted ~0, never told."""
    if reputation < SHADOW_WEIGHT_THRESHOLD:
        return 0.01
    return reputation


def judge(previous: ObservationInput, later: ObservationInput) -> bool | None:
    """Did `later` (independent, non-community-self) confirm or contradict `previous`?

    Returns None when the pair carries no signal (same contributor, or same tier gossip).
    """
    if previous.source_kind is not SourceKind.COMMUNITY:
        return None
    if later.source_kind is SourceKind.COMMUNITY and later.source_ref == previous.source_ref:
        return None
    if later.observed_at <= previous.observed_at:
        return None
    if previous.state is SpotState.UNKNOWN or later.state is SpotState.UNKNOWN:
        return None
    return previous.state is later.state
