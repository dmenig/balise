from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from balise_api.domain.enums import ReportKind, SpotState
from balise_api.schemas.common import Model, StatusOut

ReportableState = Literal["free", "occupied", "out_of_service"]


class ReportIn(Model):
    spot_id: str
    state: ReportableState
    observed_at: datetime | None = None
    report_kind: ReportKind = ReportKind.CORRECTION
    position: list[float] | None = Field(default=None, min_length=2, max_length=2)
    note: str | None = Field(default=None, max_length=280)
    client_id: str | None = None

    def spot_pk(self) -> int:
        return int(self.spot_id.removeprefix("spot_"))

    def domain_state(self) -> SpotState:
        return SpotState(self.state)


class ReportOut(Model):
    observation_id: str
    spot_id: str
    status: StatusOut
    clamped: bool
    remote: bool
    duplicate: bool = False


class BatchReportIn(Model):
    reports: list[ReportIn] = Field(max_length=100)


class BatchItemResult(Model):
    index: int
    ok: bool
    observation_id: str | None = None
    status: StatusOut | None = None
    error: str | None = None


class BatchReportOut(Model):
    accepted: int
    results: list[BatchItemResult]


class DeviceOut(Model):
    device_token: str
    note: str = "Jeton anonyme, sans donnée personnelle. Conservez-le pour retrouver vos escales."


class CommentIn(Model):
    body: str = Field(min_length=2, max_length=2000)
    rating: int | None = Field(default=None, ge=1, le=5)
    photo_keys: list[str] = Field(default_factory=list, max_length=6)


class CommentOut(Model):
    id: str
    spot_id: str | None = None
    harbour_id: str | None = None
    body: str
    rating: int | None = None
    photo_keys: list[str]
    created_at: datetime


class IssueIn(Model):
    category: Literal[
        "wrong_position", "removed", "wrong_price", "wrong_contact", "mooring_defect", "other"
    ]
    body: str = Field(min_length=2, max_length=2000)
    spot_id: str | None = None
    harbour_id: str | None = None
    nav_aid_id: str | None = None


class IssueOut(Model):
    id: str
    category: str
    created_at: datetime


class MagicLinkIn(Model):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class MagicLinkOut(Model):
    sent: bool
    #: Returned outside prod only, so the local/e2e flow does not need a mailbox.
    magic_token: str | None = None


class SessionOut(Model):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in_seconds: int
    email: str
