from __future__ import annotations

from fastapi import APIRouter, Request, Response

from balise_api import cache
from balise_api.auth.dependencies import SessionDep
from balise_api.http.etag import NotModified
from balise_api.repositories.protocols import DomainError
from balise_api.services.tiles import TileRequest, ref_version, render_tile, tile_etag

router = APIRouter(tags=["tiles"])

MVT_MEDIA_TYPE = "application/vnd.mapbox-vector-tile"
_TTL = {"navaids": 7 * 24 * 3600, "spots": 24 * 3600, "anchorages": 24 * 3600}


class TileOutOfRange(DomainError):
    status_code = 404
    title = "Tuile hors plage"


@router.get("/tiles/{layer}/{z}/{x}/{y}.mvt", response_class=Response)
async def tile(
    request: Request, session: SessionDep, layer: str, z: int, x: int, y: int
) -> Response:
    if layer not in _TTL:
        raise TileOutOfRange(f"couche {layer!r} inconnue")
    tile_request = TileRequest(layer=layer, z=z, x=x, y=y)
    if not tile_request.in_range():
        raise TileOutOfRange(f"z={z} hors plage pour {layer}")

    version = await ref_version(session)
    etag = tile_etag(version, tile_request)
    max_age = _TTL[layer]
    if request.headers.get("if-none-match") == etag:
        raise NotModified(etag, max_age)

    key = f"tile:{layer}:{version}:{z}:{x}:{y}"
    cached = await cache.get_json(key)
    if isinstance(cached, str):
        body = bytes.fromhex(cached)
    else:
        body = await render_tile(session, tile_request)
        await cache.set_json(key, body.hex(), ttl_seconds=min(max_age, 86400))
    return Response(
        content=body,
        media_type=MVT_MEDIA_TYPE,
        headers={"ETag": etag, "Cache-Control": f"public, max-age={max_age}"},
        status_code=200 if body else 204,
    )
