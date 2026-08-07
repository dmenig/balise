# Balise — cartographie des mouillages et places de port en France

> Working name: **Balise**. Web app (PWA) that shows every navigation mark, mooring buoy,
> anchorage and visitor berth in French harbours.
>
> **v1 is the referential only.** Live availability ("which ones are free") is deferred to v2 and
> built as a plug-in seam — see [docs/06](docs/06-availability-strategy.md).

This repository contains **the specification and its implementation**. `docs/` is part of the code:
every module points back at the document that justifies it, and the six availability seams are
enforced by tests rather than by good intentions.

```bash
cp .env.example .env
make up && make migrate && make seed     # PostGIS + Redis, schema, a real Morbihan fixture
make api                                 # http://localhost:8000/v1/docs
make web                                 # http://localhost:5173
```

`make seed` needs no network: it loads a checked-in extract of real SHOM and OpenStreetMap data
(918 objects around the Golfe du Morbihan, both licences represented). `make help` lists everything.

### The public map app — Streamlit, no stack needed

```bash
make streamlit                           # http://localhost:8501
```

A map-first web app, not a document with a chart in it: the deck.gl canvas fills the viewport and
every control floats over it — search, layer pills, a detail sheet that opens when you tap a mark,
a legend, night mode. Marks are drawn in **their own colour**, so a green lateral buoy is green.

It reads [`data/`](data/) directly — no PostGIS, no API, no network — so it deploys as-is on
Streamlit Community Cloud (entrypoint `streamlit_app.py`, dependencies
[`requirements.txt`](requirements.txt)). The dataset is **the whole of Bretagne and its
approaches**, from Chausey to the Loire estuary: 9 775 objects (6 500 marks, 2 254 mooring spots,
843 anchorage zones, 178 harbours) in 460 kB of Parquet. Rebuild it with `make webdata`; widen
`WEB_BBOX` to cover more coast. A gazetteer of 746 coastal places rides alongside so the
search box has somewhere to send you.

| File | Role |
|---|---|
| [`streamlit_app.py`](streamlit_app.py) | entrypoint: state, selection, camera |
| [`app/data.py`](app/data.py) | the Parquet tables, layer palette, search |
| [`app/features.py`](app/features.py) | the rows deck.gl draws, shaped for a small payload |
| [`app/deck.py`](app/deck.py) | the deck.gl scene and its picking layers |
| [`app/panels.py`](app/panels.py) | the floating chrome |
| [`app/theme.py`](app/theme.py) | the CSS that makes Streamlit a full-bleed app |

It stays a read-only shop window and deliberately **not** a second implementation: the product is
the FastAPI + PostGIS + MapLibre PWA described in [docs/07](docs/07-architecture.md).

## Read in this order

| # | Document | What it answers |
|---|---|---|
| 00 | [Vision & scope](docs/00-vision-and-scope.md) | What we build, what we explicitly do not build |
| 01 | [Glossary](docs/01-glossary.md) | `balise` vs `bouée` vs `corps-mort` vs `anneau` — read this first |
| 02 | [Personas & user stories](docs/02-personas-and-user-stories.md) | Who uses it and for what |
| 03 | [Data sources](docs/03-data-sources.md) | Where every piece of data comes from, with tested endpoints |
| 04 | [Licensing & legal](docs/04-licensing-and-legal.md) | ODbL, Etalab v2, "not for navigation", GDPR |
| 05 | [Domain model](docs/05-domain-model.md) | Entities, PostGIS schema, ID strategy |
| 06 | [Availability — deferred, kept pluggable](docs/06-availability-strategy.md) | Why v1 has no availability, the 6 seams v1 must build, and the v2 blueprint |
| 07 | [Architecture](docs/07-architecture.md) | Services, data flow, decisions |
| 08 | [API contract](docs/08-api-contract.md) | Endpoints, payloads, tiles, websocket |
| 09 | [Frontend & map](docs/09-frontend-and-map.md) | MapLibre layers, offline PWA, UX rules |
| 10 | [Ingestion pipelines](docs/10-ingestion-pipelines.md) | Fetch → normalise → conflate → load |
| 11 | [Repo structure & local setup](docs/11-repo-structure-and-setup.md) | **Build instructions** |
| 12 | [Deployment & ops](docs/12-deployment-and-ops.md) | Docker, hosting, monitoring, cost |
| 13 | [Testing & quality](docs/13-testing-and-quality.md) | Test strategy, CI gates |
| 14 | [Roadmap](docs/14-roadmap.md) | Milestones M0 → M4 with exit criteria |
| 15 | [Risks & open questions](docs/15-risks-and-open-questions.md) | What can kill the project |
| — | [MBFS v0.1 (draft)](docs/mbfs/v0.1-draft.md) | The feed spec we *show* to harbour software vendors; published in v2 |

Architecture Decision Records: [docs/adr/](docs/adr/).

## One-paragraph summary

Two data layers, very different in nature. **Layer A (référentiel)** is static, authoritative and
free to obtain: ~16 000 navigation marks (SHOM, Etalab v2) and ~14 700 OSM mooring nodes plus every
marina and anchorage in France. **This is v1, and it is a complete product on its own.**
**Layer B (disponibilité)** is dynamic and has **no public source at all** — it can only be
manufactured from partner harbour feeds, community check-ins and AIS hints, all of which take
months of partnership work. So v1 ships without it, and instead builds six cheap seams (schema,
provider port, API field, tile format, UI states, feed spec) that let Layer B be switched on later
by replacing one object. See [06](docs/06-availability-strategy.md) and [14](docs/14-roadmap.md).

## What is built

| Component | Where | State |
|---|---|---|
| PostGIS schema + migration | [api/alembic/](api/alembic/versions/) | ✅ docs/05 verbatim, incl. the empty availability tables (S1); `alembic check` clean |
| Ingestion pipelines | [ingest/](ingest/src/balise_ingest/) | ✅ SHOM WFS (16 layers), OSM (Overpass + `.osm.pbf`), ZMEL adapters, tides, weather |
| Conflation + overrides | [conflate.py](ingest/src/balise_ingest/conflate.py) · [load.py](ingest/src/balise_ingest/load.py) | ✅ per-attribute source priority, `--explain`, never-delete-on-absence, 20 % count guard |
| REST + MVT tiles | [api/routers/](api/src/balise_api/routers/) | ✅ `/spots`, `/harbours`, `/navaids`, `/tiles`, `/tides`, `/weather`, ODbL export |
| Corrections loop | [issues.py](api/src/balise_api/services/issues.py) | ✅ `POST /issues` → moderation queue → `overrides.yml` PR |
| Web PWA | [web/src/](web/src/) | ✅ map, kind/boat/shelter filters, sheets, offline download + queue, night mode, i18n, prerendered harbour pages |
| Public map app | [streamlit_app.py](streamlit_app.py) · [app/](app/) | ✅ full-bleed deck.gl map over the whole Bretagne extract, click-to-select, search, night mode, responsive; zero backend |
| Env worker | [env_worker.py](workers/src/balise_workers/env_worker.py) | ✅ tides + weather refresh on a scheduler |
| **The six seams** | [availability/](api/src/balise_api/services/availability/) · [liveUpdates.ts](web/src/map/liveUpdates.ts) | ✅ S1 empty tables · S2 provider port + null impl · S3 `status: null` and `501` · S4 status never in tiles · S5 neutral-by-kind UI · S6 MBFS drafted, unpublished |
| 🔌 v2 availability plug-in | [availability/](api/src/balise_api/services/availability/) · [tests](api/tests/v2/) | Implemented behind the seam and kept green, wired by one line when M3 starts (docs/14) |
| Ops | [ops/](ops/) | ✅ prod compose, Caddy + CSP, cron schedule, Grafana, runbooks, tile bench, Dockerfile |

## Quality gates

`make check` runs all of it. On this machine, against a real PostGIS:

| Gate | Result |
|---|---|
| `ruff format --check` + `ruff check` + `prettier` + `eslint` | clean |
| `mypy --strict api ingest workers ops` (sources, tests **and** ops scripts) | clean, 134 files |
| `tsc --noEmit` (strict, no `any`) | clean |
| v1 pytest (unit + PostGIS integration + golden files) | **116 passed** — api 53 · ingest 59 · workers 4 |
| Seam tests (docs/13) | **6 passed** — including "v1 never writes to the 🔌 tables" and "the flag has exactly one reference" |
| vitest | **25 passed** |
| Playwright, mobile viewport | **7 passed** — incl. download area → offline → read → queue a correction → reconnect → flush |
| 🔌 v2 availability suite (`make test-v2`) | **62 passed** — derivation, hypothesis properties, MBFS, decay worker |
| `make migration-roundtrip` | upgrade → downgrade → upgrade with the schema asserted at each step; `alembic check` no drift |
| Bundle budget (docs/09) | app shell 93.16 kB gzip vs 220 kB limit; MapLibre lazy-loaded |
| Tile budget (ADR-0002) | `make tiles-bench`, 3 layers × z11–z15: p95 ≤ 3 ms warm vs 300 ms |

## Status

| Item | State |
|---|---|
| SHOM WFS endpoints | ✅ verified live, no API key, GeoJSON out |
| OSM/Overpass volumes | ✅ counted over France bbox |
| Referential pipeline | ✅ fetch → normalise → conflate → load, idempotent, anomaly-guarded, re-runnable from snapshots |
| Availability | ⏸️ out of v1 scope by decision — seams built and tested, provider swap is one line (docs/06 §A) |
| Tide API (SHOM SPM) | ⚠️ client implemented, gated on `SHOM_TIDE_API_KEY`; registration terms still to confirm |
| Code | ✅ v1 complete — `make check` green |
| Data quality | ⚠️ `balise-audit` flags real gaps in the seeded bbox (71 % of harbours with no contact) — that is the M2 worklist, and it is the honest number |

## The three rules that shape everything

1. **Useful before it is live.** The referential alone is the product; availability is an increment.
2. **Honest confidence.** v1 applies this in its strongest form: rather than a bad availability, it
   shows none, and offers the capitainerie's phone and VHF channel instead.
3. **Not a navigation instrument.** The disclaimer is part of the map chrome, blocking on first use,
   and official up-to-date charts remain mandatory.

```
Fonds de carte © OpenStreetMap contributors (ODbL) — Amers et balisage : Shom, 2026 (Licence
Ouverte Etalab 2.0) — Mouillages : OpenStreetMap/OpenSeaMap (ODbL) — Marées : Shom —
Météo : Open-Meteo (CC-BY 4.0). Ne pas utiliser pour la navigation.
```
