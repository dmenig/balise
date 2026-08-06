# 07 — Architecture

## Overview

Solid boxes ship in v1. **Dashed boxes are the v2 availability plug-in**
([06](06-availability-strategy.md)) — nothing in v1 depends on them existing.

```
                    ┌──────────────────────────────────────────────┐
   External         │  SHOM WFS   OSM/Overpass   data.gouv   SHOM   │
   sources          │  (balisage) (mouillages)   (ZMEL)     marées  │
                    │  Open-Meteo         ╌ aisstream.io (WS) ╌     │
                    └───────┬──────────────────────────┬───────────┘
                            │ scheduled jobs           ╎ v2
                    ┌───────▼──────────┐      ┌╌╌╌╌╌╌╌╌▼╌╌╌╌╌╌╌╌╌┐
                    │  ingest (CLI)    │      ╎  ais-listener    ╎
                    │ fetch→normalise  │      ╎  at-rest detector╎
                    │ →conflate→load   │      └╌╌╌╌╌╌╌╌┬╌╌╌╌╌╌╌╌╌┘
                    └───────┬──────────┘               ╎
   Partners ╌╌POST╌╌╌╌╌╌╌╌► ╎ (v2)                     ╎
   (MBFS)   ◄╌╌pull╌╌╌╌╌╌╌╌ ╎                          ╎
                    ┌───────▼──────────────────────────▼───────────┐
                    │        PostgreSQL 16 + PostGIS 3.4           │
                    │  referential │ observation/status (empty v1) │
                    └───────┬───────────────────────┬──────────────┘
                            │                       │ NOTIFY (v2)
                    ┌───────▼──────────┐   ┌────────▼─────────┐
                    │  api (FastAPI)   │   │  Redis           │
                    │  REST + MVT      │◄──┤  rate limit,     │
                    │  ╌ WS (v2) ╌     │   │  tile cache,     │
                    └───────┬──────────┘   │  ╌ pub/sub (v2) ╌│
                            │              └──────────────────┘
                    ┌───────▼──────────┐
                    │  web (React PWA) │
                    │  MapLibre GL JS  │
                    └──────────────────┘
```

## Components

| Component | Tech | Responsibility | v1 |
|---|---|---|---|
| `api` | Python 3.12, FastAPI, SQLAlchemy 2 + GeoAlchemy2, Pydantic v2 | REST, vector tiles (`ST_AsMVT`), auth, data corrections | ✅ |
| `web` | TypeScript, React 18, Vite, MapLibre GL JS 4, Workbox | The whole UI, PWA, offline cache | ✅ |
| `ingest` | Python, Typer CLI, httpx, pyproj, shapely | One command per source: `fetch`, `normalise`, `conflate`, `load` | ✅ |
| `db` | PostgreSQL 16 + PostGIS 3.4 | Single source of truth, including tiles | ✅ |
| `cache` | Redis 7 | Rate limits, tile cache keys, response cache | ✅ |
| `env-worker` | Python, APScheduler | Tide + weather refresh | ✅ |
| 🔌 `status-worker` | Python, APScheduler | Decay job, status recompute, feed health | v2 |
| 🔌 `ais-listener` | Python, websockets | At-rest detection → observations | v2 |
| 🔌 websocket + pub/sub | in `api` + Redis | Live status fan-out | v2 |

`env-worker` exists in v1 anyway (tides/weather need a scheduler), so `status-worker` in v2 is a new
job in an existing process — not a new deployment unit.

**Deliberately absent**: Kafka, a separate tile server, Elasticsearch, Kubernetes, a microservice per
noun. Data volume is ~50 k referential objects and, optimistically, a few 100 k observations per
month. Postgres does all of it. Revisit only with a measured bottleneck.

## Key decisions

See [adr/](adr/) for the full records.

1. **[ADR-0001] Python/FastAPI backend, React/Vite frontend** — not Next.js: no SSR requirement
   beyond SEO harbour pages (handled by prerendering ~1 500 static pages at build), and a PWA with
   an offline map is the actual hard requirement.
2. **[ADR-0002] Vector tiles straight from PostGIS** (`ST_AsMVT`) rather than a tile server —
   ~50 k features fit trivially, tiles are cached in Redis + CDN, and status changes must invalidate
   tiles instantly.
3. **[ADR-0003] Append-only observations + derived status** *(schema in v1, writers in v2)* —
   auditability is a legal requirement ([04 §3](04-licensing-and-legal.md)) and the derivation rule
   *will* be tuned repeatedly; we must be able to recompute history.
4. **[ADR-0004] MBFS, an open GBFS-like feed spec** *(drafted in v1, published in v2)* — the only
   realistic way to onboard harbour software vendors at scale.
5. **Availability behind one provider port**, `NullAvailabilityProvider` in v1
   ([06 §A/S2](06-availability-strategy.md)). No other v1 code knows availability exists.

## Data flow — v1 read path

```
browser → CDN
  → /tiles/spots/{z}/{x}/{y}.mvt        (24 h cache, ETag on ref_version)   ← geometry + static attrs
  → /spots?bbox=…                        (list view, 60 s cache)
      api → SELECT … FROM spot LEFT JOIN spot_status USING (spot_id)        ← join present, returns NULL
          → AvailabilityProvider.status_for([...]) → {}                     ← NullAvailabilityProvider
          → serialise: {"status": null, …}
```

The join and the provider call are both in the v1 hot path, exercised on every request. That is
deliberate: the seam is load-bearing from day one, so it cannot silently break
([06 §A](06-availability-strategy.md)).

## Data flow — a status change (v2, for reference)

```
port sensor → vendor software → POST /v1/feeds/{id}/observations
  → validate token, clamp timestamps, insert observation (append-only)
  → recompute spot_status (single spot, in-transaction)
  → pg NOTIFY status_changed {spot_id, state, confidence}
  → api relays to Redis pub/sub → websocket subscribers whose bbox contains the spot
  → invalidate MVT cache keys for the tiles covering that point (z12..z16)
  → client patches the feature state in place (no map reload)
```

Target: sensor → pin turns green in the browser in **< 3 s**.

## Read path & caching

| Resource | Cache | TTL |
|---|---|---|
| `nav_aid` tiles | CDN + Redis | 7 days (immutable per ingest version, key includes `ref_version`) |
| `spot` geometry tiles | CDN + Redis | 24 h |
| `/spots` list responses | CDN + Redis | 60 s in v1 — **drops to 10 s in v2** when status becomes volatile |
| 🔌 `spot_status` overlay (JSON, bbox) | Redis | 10 s (v2) |
| harbour detail | Redis | 5 min |
| tides | DB | precomputed 7 days ahead |
| weather | DB | 1 h |

v1 is far more cacheable than v2 will be — everything it serves changes weekly at most. Budget for a
CDN hit ratio > 95 % in v1 and plan for it to fall when availability arrives.

Status is **never baked into the geometry tiles** — geometry is stable and cacheable for a day,
status is volatile and fetched separately as a compact `{id: [state, confidence, as_of]}` map. This
split is what makes the map fast on a phone with 2 bars of 4G.

## Scaling notes

- Read traffic is seasonal and coastal: 80 % of it in July–August, 17:00–19:00, along 3 coastlines.
  A CDN in front of tiles absorbs it. In v1 the app is essentially a static site with a search API.
- 🔌 Websocket connections (v2): cap at 20 k; degrade to 20 s polling above that (feature flag).
- Postgres: one primary, one read replica for tile/queries once > 5 k concurrent users. Partition
  `observation` by month at 50 M rows.
- The `ingest` jobs are the only writers to referential tables; they run nightly and are idempotent.

## Environments

`local` (docker compose) → `staging` (full data, synthetic feeds) → `prod`. Same images, config by
env vars ([11](11-repo-structure-and-setup.md)).
