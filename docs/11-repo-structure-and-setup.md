# 11 — Repo structure & local setup (build instructions)

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Python | 3.12 | via `uv` |
| **uv** | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node | 20 LTS | `nvm install 20` |
| pnpm | 9 | `corepack enable && corepack prepare pnpm@9 --activate` |
| Docker + Compose v2 | recent | — |
| osmium-tool | 1.16+ | `apt install osmium-tool` (OSM ingest only) |
| GDAL/ogr2ogr | 3.8+ | `apt install gdal-bin` (optional, data inspection) |

## Repo layout

```
balises/
├── README.md
├── docs/                        ← this specification
├── Makefile                     ← every command below has a make target
├── docker-compose.yml
├── .env.example
├── api/                         ← Python service (FastAPI)
│   ├── pyproject.toml
│   ├── src/balise_api/
│   │   ├── main.py              app factory, routers, middleware
│   │   ├── config.py            pydantic-settings
│   │   ├── db.py                engine, session, PostGIS types
│   │   ├── models/              SQLAlchemy models (mirrors docs/05)
│   │   ├── schemas/             Pydantic DTOs (API contract, docs/08)
│   │   ├── routers/             spots, harbours, navaids, tiles, issues
│   │   │   └── availability.py  🔌 stubs returning 501 (docs/06 §A/S3)
│   │   ├── services/
│   │   │   ├── tiles.py         ST_AsMVT queries
│   │   │   ├── issues.py        referential corrections → moderation queue
│   │   │   └── availability/    🔌 the seam
│   │   │       ├── provider.py  AvailabilityProvider protocol + NullAvailabilityProvider
│   │   │       └── (v2: status.py, reputation.py, realtime.py, feeds.py)
│   │   └── auth/                device tokens, magic link, harbour claims
│   ├── alembic/                 migrations (versioned SQL, incl. PostGIS DDL)
│   └── tests/
├── ingest/                      ← Python CLI (Typer)
│   ├── pyproject.toml
│   ├── src/balise_ingest/
│   │   ├── cli.py
│   │   ├── sources/{shom,osm,datagouv,tides,weather}.py
│   │   ├── adapters/zmel_*.py
│   │   ├── s57_codes.py         S-57 code → French label
│   │   ├── conflate.py
│   │   └── overrides.yml
│   └── tests/
├── streamlit_app.py             ← public map app: entrypoint (state, selection, camera)
├── app/                         ← and its modules — no PostGIS, no API, no network
│   ├── data.py                  Parquet tables, palette, place + harbour search index
│   ├── features.py              the rows deck.gl draws, shaped for a small payload
│   ├── deck.py                  the deck.gl scene, CompactDeck, picking layers
│   ├── panels.py                floating chrome: search, sheet, legend, ⓘ
│   └── theme.py                 the CSS that makes Streamlit full-bleed
├── data/                        ← what that app reads (committed, built by `make webdata`)
│   ├── points.parquet           8 932 marks, spots and harbours
│   ├── areas.parquet            843 anchorage zones
│   └── places.parquet           746 coastal places for the search box
├── workers/                     ← env-worker (tides, weather); 🔌 v2 adds status-worker, ais-listener
├── web/                         ← React PWA
│   ├── package.json
│   ├── vite.config.ts
│   ├── src/{app,map,features,components,lib,i18n}/
│   ├── public/
│   └── e2e/                     Playwright
├── ops/
│   ├── grafana/                 dashboards as JSON
│   ├── terraform/               (or ansible) infra
│   └── sql/                     ad-hoc analysis queries
└── .github/workflows/           ci.yml, deploy.yml
```

**Why a monorepo:** the API contract, the DB schema and the map styling change together in almost
every feature. Three repos would mean three PRs per change.

## First run (10 minutes)

```bash
git clone <repo> balises && cd balises
cp .env.example .env

make up            # docker compose up -d db redis  (PostGIS 16-3.4, Redis 7)
make migrate       # alembic upgrade head
make seed          # loads a small Morbihan fixture: ~40 navaids, 60 spots, 2 harbours

make api           # uv run uvicorn balise_api.main:app --reload --port 8000
make web           # pnpm --dir web dev  → http://localhost:5173
```

`make seed` uses a checked-in fixture (`ingest/fixtures/morbihan.geojson`, ~300 kB) so a new
developer never needs network access to a live source to get a working map.

## Real data locally

```bash
make ingest-shom BBOX=-3.2,47.4,-2.6,47.8     # ~2 min, no API key needed
make ingest-osm  BBOX=-3.2,47.4,-2.6,47.8     # Overpass, ~1 min for this bbox
make conflate
```

Full-France ingest (~30 min, ~2 GB of downloads) is `make ingest-all` — do it once, then work from
snapshots in `raw/`.

## Makefile targets

| Target | Does |
|---|---|
| `up` / `down` | docker compose infra |
| `migrate` / `migration m="msg"` | alembic upgrade / autogenerate |
| `seed` | load fixtures |
| `api` / `web` / `workers` | run a service in dev |
| `ingest-shom` / `ingest-osm` / `ingest-all` / `conflate` | data |
| `test` / `test-api` / `test-web` / `e2e` | tests ([13](13-testing-and-quality.md)) |
| `fmt` | `ruff format .` + `prettier --write` |
| `lint` | `ruff check .` + `ruff format --check .` + `mypy` + `eslint` + `tsc --noEmit` |
| `check` | `fmt-check lint test` — **run before every commit** |
| `tiles-bench` | measures MVT generation time per zoom |

## `.env.example`

```dotenv
# --- database
DATABASE_URL=postgresql+psycopg://balise:balise@localhost:5432/balise
REDIS_URL=redis://localhost:6379/0

# --- api
API_BASE_URL=http://localhost:8000
CORS_ORIGINS=http://localhost:5173
SECRET_KEY=change-me-32-bytes-min
DEVICE_TOKEN_SALT=change-me
ENV=local                       # local|staging|prod
LOG_LEVEL=INFO

# --- external sources
SHOM_WFS_URL=https://services.data.shom.fr/INSPIRE/wfs
SHOM_TIDE_API_KEY=              # optional; tides disabled if empty
OVERPASS_URL=https://overpass-api.de/api/interpreter
OVERPASS_USER_AGENT=balise.fr (contact@balise.fr)
GEOFABRIK_URL=https://download.geofabrik.de/europe/france-latest.osm.pbf
OPEN_METEO_URL=https://marine-api.open-meteo.com/v1/marine
AISSTREAM_API_KEY=              # optional; AIS tier disabled if empty

# --- feature flags
# v1 ships with availability off. Turning it on requires the v2 code (docs/06 §A);
# the flag exists so the seam has exactly one switch, in exactly one place.
FEATURE_AVAILABILITY=false      # false → NullAvailabilityProvider, /status & /reports → 501
FEATURE_COMMUNITY_REPORTS=false # v2
FEATURE_AIS=false               # v2
FEATURE_WEBSOCKET=false         # v2

# --- storage (photos)
S3_ENDPOINT=http://localhost:9000
S3_BUCKET=balise-media
S3_ACCESS_KEY=minio
S3_SECRET_KEY=minio123
```

Every external source is behind a flag or an empty-key check: **the app must boot and serve the
referential with no third-party credentials at all.**

`FEATURE_AVAILABILITY` is read in exactly one place — `main.py`, to choose the provider
([06 §A/S2](06-availability-strategy.md)). A `grep -rn FEATURE_AVAILABILITY api/src | wc -l` must
return `1`; a CI check enforces it. That single-reference rule is what stops the flag from
metastasising into 40 conditionals, which is how "pluggable" usually dies.

## `docker-compose.yml` (dev)

```yaml
services:
  db:
    image: postgis/postgis:16-3.4
    environment: {POSTGRES_USER: balise, POSTGRES_PASSWORD: balise, POSTGRES_DB: balise}
    ports: ["5432:5432"]
    volumes: [dbdata:/var/lib/postgresql/data]
    healthcheck: {test: ["CMD-SHELL", "pg_isready -U balise"], interval: 5s, retries: 10}
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    environment: {MINIO_ROOT_USER: minio, MINIO_ROOT_PASSWORD: minio123}
    ports: ["9000:9000", "9001:9001"]
volumes: {dbdata: {}}
```

The `api` and `web` services are added in the prod compose file ([12](12-deployment-and-ops.md));
locally they run on the host for fast reload.

## Python conventions

- Dependencies and commands go through **`uv`** (`uv add`, `uv run`, `uv sync`).
- `ruff` for lint **and** format; `ruff format --check .` is a CI gate.
- `mypy --strict` on `api/` and `ingest/`. Strict type hints, no `Any`, dataclasses/Pydantic models
  rather than bare dicts.
- Functions < 30 lines where reasonable, hard cap 50; files < 300 lines.
- Fail hard: no silent fallbacks, no `getattr`/`hasattr` probing. An unknown S-57 code raises.

## Web conventions

- TypeScript `strict: true`, no `any`, `eslint` + `@typescript-eslint`.
- API types **generated** from the OpenAPI schema (`pnpm gen:api`) — never hand-written.
- No component over 200 lines; map layer definitions live in `src/map/layers/*.ts` as data, not JSX.

## Common problems

| Symptom | Cause / fix |
|---|---|
| `could not find function ST_AsMVT` | Wrong image; must be `postgis/postgis`, not `postgres` |
| Empty map, 200 responses | `ref_version` not bumped after ingest → stale ETag; `make tiles-flush` |
| Overpass 429 | Set `OVERPASS_USER_AGENT`, back off, or use the pbf path |
| SHOM WFS returns XML instead of JSON | `outputFormat=application/json` missing/misspelled |
| Alembic can't autogenerate PostGIS columns | `include_object` filter in `env.py` must skip `spatial_ref_sys` |
