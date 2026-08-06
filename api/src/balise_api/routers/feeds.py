from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from balise_api.auth.dependencies import FeedDep, SessionDep
from balise_api.repositories.feeds import SqlFeedRepository
from balise_api.repositories.sql import (
    SqlObservationRepository,
    SqlSpotRepository,
    SqlStatusRepository,
)
from balise_api.schemas.feeds import (
    FeedHealthOut,
    FeedIngestOut,
    MbfsSnapshot,
    ObservationsIn,
    RejectionOut,
)
from balise_api.services.availability import feeds as feed_service
from balise_api.services.availability.realtime import RedisStatusPublisher

router = APIRouter(tags=["feeds"], prefix="/feeds")


def _context(session: SessionDep) -> feed_service.FeedContext:
    return feed_service.FeedContext(
        feeds=SqlFeedRepository(session),
        spots=SqlSpotRepository(session),
        observations=SqlObservationRepository(session),
        statuses=SqlStatusRepository(session),
        publisher=RedisStatusPublisher(),
    )


@router.post("/{feed_id}/observations", response_model=FeedIngestOut)
async def post_observations(
    feed_id: str, payload: ObservationsIn, session: SessionDep, feed: FeedDep
) -> FeedIngestOut:
    items = [
        feed_service.FeedSpotObservation(
            spot_id=item.spot_id,
            state=item.domain_state(),
            observed_at=item.observed_at,
            until=item.until,
            max_loa_m=item.max_loa_m,
            max_draft_m=item.max_draft_m,
        )
        for item in payload.observations
    ]
    result = await feed_service.ingest_spot_observations(
        _context(session), feed, items, datetime.now(UTC)
    )
    await session.commit()
    return FeedIngestOut(
        accepted=result.accepted,
        rejected=[RejectionOut(index=r.index, reason=r.reason) for r in result.rejected],
    )


@router.put("/{feed_id}/snapshot", response_model=FeedIngestOut)
async def put_snapshot(
    feed_id: str, payload: MbfsSnapshot, session: SessionDep, feed: FeedDep
) -> FeedIngestOut:
    """Full-state replacement — simpler for a vendor than computing deltas (docs/08)."""
    fields = [
        feed_service.FeedFieldObservation(
            field_id=field.field_id,
            num_free=field.num_free,
            capacity=field.capacity,
            visitor_capacity=field.visitor_capacity,
            last_reported=field.last_reported or payload.last_updated,
            spots=tuple(
                feed_service.FeedSpotObservation(
                    spot_id=spot.spot_id,
                    state=spot.domain_state(),
                    observed_at=spot.observed_at or field.last_reported or payload.last_updated,
                    until=spot.until,
                    max_loa_m=spot.max_loa_m,
                    max_draft_m=spot.max_draft_m,
                )
                for spot in field.spots
            ),
        )
        for harbour in payload.data.harbours
        for field in harbour.fields
    ]
    result = await feed_service.apply_snapshot(_context(session), feed, fields, datetime.now(UTC))
    await session.commit()
    return FeedIngestOut(
        accepted=result.accepted,
        rejected=[RejectionOut(index=r.index, reason=r.reason) for r in result.rejected],
    )


@router.get("/{feed_id}/health", response_model=FeedHealthOut)
async def health(feed_id: str, session: SessionDep, feed: FeedDep) -> FeedHealthOut:
    """Given to the partner so they can monitor themselves (docs/08)."""
    payload = await SqlFeedRepository(session).health(feed_id, datetime.now(UTC))
    return FeedHealthOut.model_validate(payload)
