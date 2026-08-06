# ADR-0001 — Python/FastAPI backend, React + MapLibre PWA frontend

**Status:** Accepted — 2026-08-06

## Context

The product is a geospatial data application: heavy ingestion and transformation of open data
(WFS, OSM PBF, GRIB-adjacent), a spatial database, and a map UI that must work on a phone at sea
with intermittent connectivity. The team's existing Python tooling is `uv` + `ruff` + `pytest`.

## Decision

- **Backend: Python 3.12 + FastAPI + SQLAlchemy 2 + GeoAlchemy2 + Pydantic v2.**
- **Frontend: React 18 + TypeScript + Vite + MapLibre GL JS 4, shipped as a PWA.**
- **Not Next.js.**

## Consequences

- The ingestion stack (shapely, pyproj, osmium bindings, pandas where needed) and the API share one
  language, one dependency manager and one test runner. Geospatial Python is mature; the equivalent
  in Node is not.
- FastAPI gives us the OpenAPI schema for free, from which frontend types are generated — one
  contract, no drift.
- No SSR runtime to operate. SEO for the ~1 500 `/port/{slug}` pages is handled by build-time
  prerendering, which is enough for content that changes daily at most.
- Offline is a first-class capability: a service worker plus IndexedDB under our full control, with
  no framework-imposed data-fetching model to fight.
- Cost: we forgo Next.js conveniences (image optimisation, route handlers) and must assemble
  routing/prerender ourselves. Acceptable at this app's size.

## Alternatives rejected

| Option | Why not |
|---|---|
| Next.js full-stack (TS everywhere) | SSR adds a runtime to operate for no user-visible gain here, and the ingestion side would still be Python — the "one language" benefit does not materialise |
| Django + GeoDjango | Excellent geospatial ORM, but the app is API + tiles + websockets, not server-rendered forms; DRF adds ceremony we do not need |
| Go backend | Faster tiles, but the ingestion ecosystem (shapely/pyproj/osmium) and the team's fluency are in Python |
| Mapbox GL JS | Licence and per-load pricing; MapLibre is the free fork and covers everything we need |
| Leaflet | Raster-oriented; no `setFeatureState`, no efficient client-side styling of 10 k features |
