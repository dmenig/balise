from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Header, status

from balise_api.auth.dependencies import ContributorDep, SessionDep
from balise_api.models import Comment
from balise_api.repositories.protocols import DomainError
from balise_api.repositories.sql import (
    SqlContributorRepository,
    SqlObservationRepository,
    SqlSpotRepository,
    SqlStatusRepository,
)
from balise_api.schemas.common import StatusOut
from balise_api.schemas.reports import (
    BatchItemResult,
    BatchReportIn,
    BatchReportOut,
    CommentIn,
    CommentOut,
    ReportIn,
    ReportOut,
)
from balise_api.services.availability.community import (
    ReportContext,
    ReportSubmission,
    submit_report,
)
from balise_api.services.availability.realtime import RedisStatusPublisher

router = APIRouter(tags=["contribution"])


def _context(session: SessionDep) -> ReportContext:
    return ReportContext(
        spots=SqlSpotRepository(session),
        observations=SqlObservationRepository(session),
        statuses=SqlStatusRepository(session),
        contributors=SqlContributorRepository(session),
        publisher=RedisStatusPublisher(),
    )


def _submission(payload: ReportIn, idempotency_key: str | None, now: datetime) -> ReportSubmission:
    position = (payload.position[0], payload.position[1]) if payload.position else None
    return ReportSubmission(
        spot_id=payload.spot_pk(),
        state=payload.domain_state(),
        observed_at=payload.observed_at or now,
        report_kind=payload.report_kind,
        position=position,
        note=payload.note,
        idempotency_key=idempotency_key,
    )


@router.post("/reports", response_model=ReportOut, status_code=status.HTTP_201_CREATED)
async def create_report(
    payload: ReportIn,
    session: SessionDep,
    contributor: ContributorDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> ReportOut:
    now = datetime.now(UTC)
    outcome = await submit_report(
        _context(session), _submission(payload, idempotency_key, now), contributor, now
    )
    await session.commit()
    return ReportOut(
        observation_id=f"obs_{outcome.observation_id}",
        spot_id=payload.spot_id,
        status=StatusOut.from_derived(outcome.status, now),
        clamped=outcome.clamped,
        remote=outcome.remote,
        duplicate=outcome.duplicate,
    )


@router.post("/reports/batch", response_model=BatchReportOut)
async def create_reports_batch(
    payload: BatchReportIn, session: SessionDep, contributor: ContributorDep
) -> BatchReportOut:
    """Offline flush. Partial success per item; one bad report never loses the others."""
    now = datetime.now(UTC)
    context = _context(session)
    results: list[BatchItemResult] = []
    accepted = 0
    for index, item in enumerate(payload.reports):
        try:
            outcome = await submit_report(
                context, _submission(item, item.client_id, now), contributor, now
            )
        except DomainError as exc:
            await session.rollback()
            results.append(BatchItemResult(index=index, ok=False, error=str(exc)))
            continue
        accepted += 1
        results.append(
            BatchItemResult(
                index=index,
                ok=True,
                observation_id=f"obs_{outcome.observation_id}",
                status=StatusOut.from_derived(outcome.status, now),
            )
        )
    await session.commit()
    return BatchReportOut(accepted=accepted, results=results)


@router.post(
    "/spots/{spot_id}/comments", response_model=CommentOut, status_code=status.HTTP_201_CREATED
)
async def create_comment(
    spot_id: str, payload: CommentIn, session: SessionDep, contributor: ContributorDep
) -> CommentOut:
    row = Comment(
        spot_id=int(spot_id.removeprefix("spot_")),
        contributor_id=contributor.id,
        body=payload.body,
        rating=payload.rating,
        photo_keys=payload.photo_keys,
    )
    session.add(row)
    await session.commit()
    return CommentOut(
        id=f"comment_{row.id}",
        spot_id=spot_id,
        body=row.body,
        rating=row.rating,
        photo_keys=list(row.photo_keys),
        created_at=row.created_at,
    )
