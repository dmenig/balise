from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from balise_api.auth.dependencies import SessionDep
from balise_api.dependencies import AvailabilityDep
from balise_api.http.etag import apply_etag
from balise_api.queries import environment, harbours
from balise_api.repositories.protocols import DomainError
from balise_api.schemas.harbours import HarbourDetail, HarbourList
from balise_api.schemas.spots import TideSummary, WeatherSummary

router = APIRouter(tags=["harbours"])


class InvalidQuery(DomainError):
    status_code = 422
    title = "Paramètre invalide"


def _parse_near(near: str | None) -> tuple[float, float] | None:
    if not near:
        return None
    parts = near.split(",")
    if len(parts) != 2:
        raise InvalidQuery("near attend lon,lat")
    try:
        return float(parts[0]), float(parts[1])
    except ValueError as exc:
        raise InvalidQuery("near attend lon,lat") from exc


@router.get("/harbours", response_model=HarbourList)
async def search(
    request: Request,
    response: Response,
    session: SessionDep,
    q: Annotated[str | None, Query(min_length=2, max_length=80)] = None,
    near: Annotated[str | None, Query(description="lon,lat")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
) -> HarbourList:
    payload = await harbours.search_harbours(session, q, _parse_near(near), limit)
    apply_etag(request, response, payload.model_dump_json(), max_age=60)
    return payload


@router.get("/harbours/{slug}", response_model=HarbourDetail)
async def detail(
    request: Request,
    response: Response,
    session: SessionDep,
    availability: AvailabilityDep,
    slug: str,
) -> HarbourDetail:
    payload = await harbours.get_harbour(session, slug, availability)
    apply_etag(request, response, payload.model_dump_json(), max_age=300)
    return payload


@router.get("/tides", response_model=list[dict[str, object]])
async def tides(
    session: SessionDep,
    harbour: Annotated[str, Query(description="harbour slug")],
    from_at: Annotated[datetime | None, Query(alias="from")] = None,
    to_at: Annotated[datetime | None, Query(alias="to")] = None,
) -> list[dict[str, object]]:
    harbour_id = await harbours.harbour_id_for_slug(session, harbour)
    start = from_at or datetime.now(UTC)
    end = to_at or start + timedelta(days=7)
    extremes = await environment.tide_range(session, harbour_id, start, end)
    return [extreme.model_dump(mode="json") | {"is_estimate": True} for extreme in extremes]


@router.get("/tides/summary", response_model=TideSummary | None)
async def tide_summary(
    session: SessionDep,
    harbour: Annotated[str, Query()],
    charted_depth_m: Annotated[float | None, Query()] = None,
) -> TideSummary | None:
    harbour_id = await harbours.harbour_id_for_slug(session, harbour)
    return await environment.tide_summary(session, harbour_id, datetime.now(UTC), charted_depth_m)


@router.get("/weather", response_model=WeatherSummary | None)
async def weather(
    session: SessionDep,
    harbour: Annotated[str, Query()],
    hours: Annotated[int, Query(ge=1, le=168)] = 48,
) -> WeatherSummary | None:
    harbour_id = await harbours.harbour_id_for_slug(session, harbour)
    return await environment.weather_summary(session, harbour_id, datetime.now(UTC), hours)
