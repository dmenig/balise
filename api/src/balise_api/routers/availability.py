"""🔌 The availability surface: specified in v1, implemented in v2 (docs/06 §A/S3, docs/08).

Every route here exists in the OpenAPI schema — with its real request model, so the generated
frontend types and the docs never need a breaking change — and returns
`501 availability_not_enabled` until the v2 provider is wired.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, WebSocket
from fastapi.responses import JSONResponse

from balise_api.http.problems import AVAILABILITY_NOT_ENABLED, availability_not_enabled
from balise_api.schemas.feeds import MbfsSnapshot, ObservationsIn
from balise_api.schemas.reports import BatchReportIn, CommentIn, ReportIn

router = APIRouter(tags=["availability (v2)"])

_RESPONSES: dict[int | str, dict[str, object]] = {
    501: {
        "description": "Availability is not enabled",
        "content": {"application/problem+json": {"example": AVAILABILITY_NOT_ENABLED}},
    }
}


@router.get("/status", responses=_RESPONSES, summary="Status overlay (v2)")
async def status_map(
    bbox: Annotated[str, Query()],
    since: Annotated[datetime | None, Query()] = None,
) -> JSONResponse:
    return availability_not_enabled()


@router.post("/reports", responses=_RESPONSES, summary="Community report (v2)")
async def create_report(payload: ReportIn) -> JSONResponse:
    return availability_not_enabled()


@router.post("/reports/batch", responses=_RESPONSES, summary="Offline report flush (v2)")
async def create_reports_batch(payload: BatchReportIn) -> JSONResponse:
    return availability_not_enabled()


@router.post("/spots/{spot_id}/comments", responses=_RESPONSES, summary="Spot comment (v2)")
async def create_comment(spot_id: str, payload: CommentIn) -> JSONResponse:
    return availability_not_enabled()


@router.post("/uploads", responses=_RESPONSES, summary="Photo upload (v2)")
async def upload_photo() -> JSONResponse:
    return availability_not_enabled()


@router.post("/feeds/{feed_id}/observations", responses=_RESPONSES, summary="MBFS deltas (v2)")
async def post_observations(feed_id: str, payload: ObservationsIn) -> JSONResponse:
    return availability_not_enabled()


@router.put("/feeds/{feed_id}/snapshot", responses=_RESPONSES, summary="MBFS snapshot (v2)")
async def put_snapshot(feed_id: str, payload: MbfsSnapshot) -> JSONResponse:
    return availability_not_enabled()


@router.get("/feeds/{feed_id}/health", responses=_RESPONSES, summary="Feed health (v2)")
async def feed_health(feed_id: str) -> JSONResponse:
    return availability_not_enabled()


@router.get("/opendata/mbfs", responses=_RESPONSES, summary="MBFS spec (published in v2)")
async def mbfs_spec() -> JSONResponse:
    """Drafted in `docs/mbfs/` in v1 (docs/06 §A/S6): publishing a spec with zero implementers is a
    maintenance liability, and its v1 job is to be shown to capitaineries, not to be served."""
    return availability_not_enabled()


@router.get("/opendata/stats.json", responses=_RESPONSES, summary="Aggregate occupancy (v2)")
async def stats() -> JSONResponse:
    return availability_not_enabled()


@router.websocket("/stream")
async def stream(socket: WebSocket) -> None:
    """v1 has no websocket. The client's data layer is written against `subscribe(bbox, onUpdate)`
    whose v1 implementation is a no-op (docs/08), so our own app never reaches this refusal."""
    await socket.accept()
    await socket.send_json(AVAILABILITY_NOT_ENABLED)
    await socket.close(code=1011)
