from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from balise_api.auth.dependencies import SessionDep
from balise_api.dependencies import AvailabilityDep
from balise_api.domain.enums import SpotKind
from balise_api.http.etag import apply_etag
from balise_api.http.problems import AVAILABILITY_NOT_ENABLED, availability_not_enabled
from balise_api.queries import environment, spots
from balise_api.repositories.protocols import DomainError
from balise_api.schemas.common import BboxValue, FeatureCollection
from balise_api.schemas.spots import SpotDetail

router = APIRouter(tags=["spots"])


class InvalidQuery(DomainError):
    status_code = 422
    title = "Paramètre invalide"


def _parse_bbox(raw: str, max_span_deg: float) -> BboxValue:
    try:
        return BboxValue.parse(raw, max_span_deg)
    except ValueError as exc:
        raise InvalidQuery(f"bbox: {exc}") from exc


def _kinds(raw: str | None) -> tuple[SpotKind, ...]:
    if not raw:
        return ()
    try:
        return tuple(SpotKind(value.strip()) for value in raw.split(",") if value.strip())
    except ValueError as exc:
        raise InvalidQuery(str(exc)) from exc


def _sectors(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    sectors = tuple(value.strip().upper() for value in raw.split(",") if value.strip())
    unknown = [sector for sector in sectors if sector not in spots.SECTORS]
    if unknown:
        raise InvalidQuery(f"secteurs inconnus: {', '.join(unknown)} (attendu: N, NE, E, SE, …)")
    return sectors


@router.get(
    "/spots",
    response_model=FeatureCollection,
    responses={
        501: {"content": {"application/problem+json": {"example": AVAILABILITY_NOT_ENABLED}}}
    },
)
async def list_spots(
    request: Request,
    response: Response,
    session: SessionDep,
    availability: AvailabilityDep,
    bbox: Annotated[str, Query(description="min_lon,min_lat,max_lon,max_lat — 2° max")],
    kind: Annotated[
        str | None, Query(description="csv: mooring_buoy,berth,anchorage,pile,quay")
    ] = None,
    max_draft_m: Annotated[float | None, Query(gt=0, le=20, description="boat draught")] = None,
    max_loa_m: Annotated[float | None, Query(gt=0, le=200, description="boat length")] = None,
    visitor: Annotated[bool | None, Query()] = None,
    sheltered_from: Annotated[
        str | None, Query(description="csv of wind sectors, e.g. NW,N")
    ] = None,
    sort: Annotated[spots.SortKey, Query()] = "distance",
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    cursor: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query(description="🔌 v2 — availability filter")] = None,
    min_confidence: Annotated[
        float | None, Query(description="🔌 v2 — availability filter")
    ] = None,
) -> FeatureCollection | Response:
    # 🔌 Availability filters are specified now and refuse politely until v2 (docs/06 §A/S3).
    if state is not None or min_confidence is not None:
        return availability_not_enabled()

    filters = spots.SpotFilters(
        bbox=_parse_bbox(bbox, 2.0),
        kinds=_kinds(kind),
        max_draft_m=max_draft_m,
        max_loa_m=max_loa_m,
        visitor=visitor,
        sheltered_from=_sectors(sheltered_from),
        sort=sort,
        limit=limit,
        cursor=int(cursor) if cursor else None,
    )
    payload = await spots.list_spots(session, filters, availability)
    # 60 s in v1; drops to 10 s in v2 when status becomes volatile (docs/07).
    apply_etag(request, response, payload.model_dump_json(), max_age=60)
    return payload


@router.get("/spots/{spot_id}", response_model=SpotDetail)
async def get_spot(
    request: Request,
    response: Response,
    session: SessionDep,
    availability: AvailabilityDep,
    spot_id: str,
) -> SpotDetail:
    now = datetime.now(UTC)
    detail = await spots.get_spot(session, int(spot_id.removeprefix("spot_")), availability)
    harbour_pk = (
        int(detail.harbour.id.removeprefix("harbour_"))
        if detail.harbour
        else await environment.nearest_harbour_id(session, *detail.position)
    )
    if harbour_pk is not None:
        detail = detail.model_copy(
            update={
                "tide": await environment.tide_summary(
                    session, harbour_pk, now, detail.properties.depth_m
                ),
                "weather": await environment.weather_summary(session, harbour_pk, now),
            }
        )
    # The sheet reserves a status slot (docs/09): it is `null` in v1 and populated in v2, so no
    # cache policy or layout changes when availability arrives.
    apply_etag(request, response, detail.model_dump_json(), max_age=60)
    return detail
