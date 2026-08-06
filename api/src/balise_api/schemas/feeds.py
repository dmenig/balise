"""MBFS v0.1 payloads (docs/06, ADR-0004). Field-level counts alone are a valid payload."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from balise_api.domain.enums import SpotState
from balise_api.schemas.common import Model

MBFS_VERSION = "0.1"
FeedState = Literal["free", "occupied", "reserved", "out_of_service"]


class MbfsSpot(Model):
    spot_id: str
    state: FeedState
    observed_at: datetime | None = None
    until: datetime | None = None
    max_loa_m: float | None = None
    max_draft_m: float | None = None

    def domain_state(self) -> SpotState:
        return SpotState(self.state)


class MbfsField(Model):
    field_id: str
    capacity: int | None = Field(default=None, ge=0)
    visitor_capacity: int | None = Field(default=None, ge=0)
    num_free: int | None = Field(default=None, ge=0)
    last_reported: datetime | None = None
    spots: list[MbfsSpot] = Field(default_factory=list)


class MbfsHarbour(Model):
    harbour_id: str
    fields: list[MbfsField]


class MbfsData(Model):
    harbours: list[MbfsHarbour]


class MbfsSnapshot(Model):
    last_updated: datetime
    ttl: int = Field(ge=1, le=3600)
    version: str = MBFS_VERSION
    data: MbfsData


class ObservationsIn(Model):
    observations: list[MbfsSpot] = Field(max_length=5000)


class RejectionOut(Model):
    index: int
    reason: str


class FeedIngestOut(Model):
    accepted: int
    rejected: list[RejectionOut]


class FeedHealthOut(Model):
    feed_id: str
    last_received: datetime | None
    ttl_seconds: int
    staleness_seconds: float | None
    stale: bool
    observations_24h: int
    accepted_24h: int
    rejected_24h: int
    rejection_rate_24h: float
