from __future__ import annotations

import json

from fastapi import APIRouter, Response
from sqlalchemy import text

from balise_api import attribution
from balise_api.auth.dependencies import SessionDep

router = APIRouter(tags=["opendata"], prefix="/opendata")

#: Quarterly ODbL share-alike discharge (docs/04 §2): only the OSM-derived part, never Layer B.
_OSM_EXPORT_SQL = """
SELECT json_build_object(
  'type', 'FeatureCollection',
  'licence', 'ODbL-1.0',
  'attribution', CAST(:attribution AS text),
  'features', COALESCE(json_agg(feature), '[]'::json)
) AS payload
FROM (
  SELECT json_build_object(
    'type', 'Feature',
    'id', 'spot_' || s.id,
    'geometry', ST_AsGeoJSON(s.geom)::json,
    'properties', json_build_object(
      'kind', s.kind::text, 'code', s.code, 'depth_m', s.depth_m,
      'max_loa_m', s.max_loa_m, 'max_draft_m', s.max_draft_m, 'visitor', s.visitor,
      'external_ids', s.external_ids, 'source_id', s.source_id
    )
  ) AS feature
  FROM spot s
  WHERE s.active AND s.source_id LIKE 'osm%'
  UNION ALL
  SELECT json_build_object(
    'type', 'Feature',
    'id', 'harbour_' || h.id,
    'geometry', ST_AsGeoJSON(h.geom)::json,
    'properties', json_build_object(
      'name', h.name, 'slug', h.slug, 'vhf_channel', h.vhf_channel,
      'services', h.services, 'external_ids', h.external_ids, 'source_id', h.source_id
    )
  ) AS feature
  FROM harbour h
  WHERE h.source_id LIKE 'osm%'
) features
"""


@router.get("/referential-osm.geojson")
async def referential_osm(session: SessionDep) -> Response:
    row = await session.execute(text(_OSM_EXPORT_SQL), {"attribution": attribution.OSM})
    payload = row.scalar_one()
    body = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return Response(
        content=body,
        media_type="application/geo+json",
        headers={"Cache-Control": "public, max-age=86400"},
    )
