"""v1 contribution: `POST /issues` — referential corrections into a moderation queue (docs/08)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, status
from pydantic import Field
from sqlalchemy import text

from balise_api.auth.dependencies import ContributorDep, SessionDep
from balise_api.auth.tokens import issue_device_token
from balise_api.schemas.common import Model
from balise_api.services import issues

router = APIRouter(tags=["contribution"])


class IssueTarget(Model):
    type: issues.TargetType
    id: str

    def primary_key(self) -> int:
        return int(self.id.split("_", 1)[-1])


class IssueIn(Model):
    target: IssueTarget
    kind: issues.IssueKind
    note: Annotated[str, Field(min_length=2, max_length=2000)]
    position: Annotated[list[float] | None, Field(default=None, min_length=2, max_length=2)] = None
    client_id: str | None = None


class IssueOut(Model):
    id: str
    kind: str
    created_at: datetime
    note: str = "Merci — votre signalement part en revue avant d'être appliqué au référentiel."


class DeviceOut(Model):
    device_token: str
    note: str = "Jeton anonyme, sans donnée personnelle. Conservez-le pour suivre vos signalements."


@router.post("/devices", response_model=DeviceOut, status_code=status.HTTP_201_CREATED)
async def create_device() -> DeviceOut:
    """Anonymous, PII-free identity for corrections (docs/08 auth table)."""
    return DeviceOut(device_token=issue_device_token())


@router.delete("/me", status_code=status.HTTP_202_ACCEPTED)
async def erase_me(session: SessionDep, contributor: ContributorDep) -> dict[str, str]:
    """GDPR self-service erasure (docs/04 §4): the account goes, the corrections stay anonymised."""
    await session.execute(
        text("UPDATE issue SET contributor_id = NULL WHERE contributor_id = :cid"),
        {"cid": contributor.id},
    )
    await session.execute(text("DELETE FROM contributor WHERE id = :cid"), {"cid": contributor.id})
    await session.commit()
    return {"status": "erased"}


@router.post("/issues", response_model=IssueOut, status_code=status.HTTP_202_ACCEPTED)
async def create_issue(
    payload: IssueIn, session: SessionDep, contributor: ContributorDep
) -> IssueOut:
    """`202` into the moderation queue → reviewed → lands as a PR on `overrides.yml` (docs/10)."""
    position = (payload.position[0], payload.position[1]) if payload.position else None
    correction = issues.Correction(
        target_type=payload.target.type,
        target_id=payload.target.primary_key(),
        kind=payload.kind,
        note=payload.note,
        position=position,
    )
    created = await issues.submit(session, correction, contributor.id)
    await session.commit()
    return IssueOut(id=str(created["id"]), kind=payload.kind, created_at=created["created_at"])
