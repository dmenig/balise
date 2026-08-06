# ADR-0002 — Serve vector tiles directly from PostGIS

**Status:** Accepted — 2026-08-06

## Context

The map renders ~16 000 navigation marks and a few tens of thousands of spots. Geometry is stable
(changes weekly at most); **status is volatile** (changes in seconds). We need both on the same map
without re-downloading geometry every time a buoy frees up.

## Decision

Generate MVT tiles in the API with `ST_AsMVT`, cached in Redis and on the CDN.
**Status is never embedded in tiles.** It is fetched separately as a compact
`{spot_id: [state, confidence, as_of, source]}` map and joined client-side with MapLibre's
`setFeatureState`.

```sql
SELECT ST_AsMVT(t, 'spots', 4096, 'geom') FROM (
  SELECT s.id,
         ST_AsMVTGeom(s.geom, ST_TileEnvelope(:z,:x,:y), 4096, 64, true) AS geom,
         s.kind, s.code, s.depth_m, s.max_loa_m, s.max_draft_m, s.visitor
  FROM spot s
  WHERE s.active AND s.geom && ST_Transform(ST_TileEnvelope(:z,:x,:y), 4326)
) t;
```

## Consequences

- Geometry tiles are cacheable for 24 h (spots) / 7 days (nav aids) with an ETag keyed on
  `ref_version`; a re-ingest bumps it and invalidates everything cleanly.
- Status payloads are tiny (~30 kB gzip for a 0.5° bbox) and refresh every 10 s or over the
  websocket — which is what makes the map usable on a weak 4G link.
- One less service to deploy, monitor and version than a tile server.
- Tile generation cost is a DB query; measured budget p95 < 300 ms per tile, mostly absorbed by the
  CDN. `tiles-bench` in the Makefile guards this.
- If tile generation ever becomes the bottleneck, the escape hatch is pre-generating a PMTiles
  archive for the static referential — the client contract does not change.

## Alternatives rejected

| Option | Why not |
|---|---|
| pg_tileserv / Martin | Another service, another deploy, for a query we can write in 10 lines |
| Tegola | Same, plus a config format to learn |
| GeoJSON over the wire | 16 k features per viewport kills mobile parse time and memory |
| Status baked into tiles | Would make tiles uncacheable — the exact opposite of what we need |
