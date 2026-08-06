"""MVT generation straight from PostGIS (ADR-0002). Status is never baked into a tile."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

NAVAID_ZOOM = (8, 16)
SPOT_ZOOM = (10, 18)
EXTENT = 4096
BUFFER = 64

_NAVAID_SQL = text(
    """
    SELECT ST_AsMVT(t, 'navaids', :extent, 'geom') AS tile FROM (
      SELECT n.id,
             ST_AsMVTGeom(n.geom, ST_Transform(ST_TileEnvelope(:z, :x, :y), 4326),
                          :extent, :buffer, true) AS geom,
             n.s57_class, n.name, n.colour, n.shape, n.topmark, n.category,
             (n.light IS NOT NULL) AS lit
      FROM nav_aid n
      WHERE n.active
        AND n.geom && ST_Transform(ST_TileEnvelope(:z, :x, :y, margin => 0.03125), 4326)
    ) t
    """
)

_SPOT_SQL = text(
    """
    SELECT ST_AsMVT(t, 'spots', :extent, 'geom') AS tile FROM (
      SELECT s.id,
             ST_AsMVTGeom(s.geom, ST_Transform(ST_TileEnvelope(:z, :x, :y), 4326),
                          :extent, :buffer, true) AS geom,
             s.kind::text AS kind, s.code, s.depth_m, s.max_loa_m, s.max_draft_m,
             s.visitor, s.field_id, s.harbour_id
      FROM spot s
      WHERE s.active
        AND s.geom && ST_Transform(ST_TileEnvelope(:z, :x, :y, margin => 0.03125), 4326)
    ) t
    """
)

_ANCHORAGE_SQL = text(
    """
    SELECT ST_AsMVT(t, 'anchorages', :extent, 'geom') AS tile FROM (
      SELECT f.id,
             ST_AsMVTGeom(f.area, ST_Transform(ST_TileEnvelope(:z, :x, :y), 4326),
                          :extent, :buffer, true) AS geom,
             f.name, f.capacity, f.kind::text AS kind
      FROM field f
      WHERE f.area IS NOT NULL
        AND f.area && ST_Transform(ST_TileEnvelope(:z, :x, :y, margin => 0.03125), 4326)
    ) t
    """
)

_LAYERS = {"navaids": _NAVAID_SQL, "spots": _SPOT_SQL, "anchorages": _ANCHORAGE_SQL}


@dataclass(frozen=True, slots=True)
class TileRequest:
    layer: str
    z: int
    x: int
    y: int

    def in_range(self) -> bool:
        bounds = NAVAID_ZOOM if self.layer == "navaids" else SPOT_ZOOM
        if not bounds[0] <= self.z <= bounds[1]:
            return False
        limit = 1 << self.z
        return 0 <= self.x < limit and 0 <= self.y < limit


async def render_tile(session: AsyncSession, request: TileRequest) -> bytes:
    statement = _LAYERS[request.layer]
    result = await session.execute(
        statement,
        {"z": request.z, "x": request.x, "y": request.y, "extent": EXTENT, "buffer": BUFFER},
    )
    tile = result.scalar_one()
    return bytes(tile) if tile is not None else b""


async def ref_version(session: AsyncSession) -> str:
    row = await session.execute(text("SELECT value FROM meta WHERE key = 'ref_version'"))
    value = row.scalar_one_or_none()
    return str(value) if value is not None else "0"


def tile_etag(version: str, request: TileRequest) -> str:
    return f'W/"{request.layer}-{version}-{request.z}-{request.x}-{request.y}"'
