from __future__ import annotations

from fastapi import APIRouter, Request, Response

from balise_api.auth.dependencies import SessionDep
from balise_api.http.etag import apply_etag
from balise_api.queries import navaids
from balise_api.schemas.navaids import NavAidDetail

router = APIRouter(tags=["navaids"])


@router.get("/navaids/{nav_aid_id}", response_model=NavAidDetail)
async def get_navaid(
    request: Request, response: Response, session: SessionDep, nav_aid_id: str
) -> NavAidDetail:
    payload = await navaids.get_navaid(session, int(nav_aid_id.removeprefix("navaid_")))
    apply_etag(request, response, payload.model_dump_json(), max_age=86400)
    return payload


@router.get("/navaids", response_model=list[str])
async def list_ids(session: SessionDep, limit: int = 5000) -> list[str]:
    """Ids only — the map reads nav aids from tiles; this feeds the SEO prerender."""
    return [f"navaid_{value}" for value in await navaids.navaid_ids(session, limit)]
