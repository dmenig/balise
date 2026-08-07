SHELL := /bin/bash
.DEFAULT_GOAL := help
.PHONY: help up down migrate migration seed api web workers worker-once ais \
        ingest-shom ingest-osm ingest-zmel ingest-all ingest-tides ingest-weather conflate \
        fixture webdata audit admin mbfs test test-v1 test-v2 test-api test-ingest test-workers test-web \
        e2e e2e-install seam \
        streamlit \
        fmt fmt-check lint typecheck check tiles-flush tiles-bench prerender build-web \
        migration-roundtrip \
        openapi gen-api db-shell logs clean

PNPM ?= pnpm
WEB := $(PNPM) --dir web
BBOX ?= -3.2,47.4,-2.6,47.8
#: Bretagne plus its approaches: Chausey and the Cotentin west coast to the Loire estuary.
WEB_BBOX ?= -5.4,47.15,-1.0,49.0
DEPT ?= 56
# The host port comes from .env, like docker compose does: a machine with a postgres already on
# 5432 publishes elsewhere, and `make check` must still find *our* database (docs/11).
DB_PORT ?= $(or $(shell sed -n 's/^DB_PORT=\([0-9]\{1,\}\).*/\1/p' .env 2>/dev/null),5432)
TEST_DB ?= postgresql+psycopg://balise:balise@localhost:$(DB_PORT)/balise_test

help: ## List every target
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# --- infrastructure ---------------------------------------------------------
up: ## Start db, redis and minio (PostGIS 16-3.4, Redis 7)
	docker compose up -d db redis minio
	@# -h 127.0.0.1 on purpose: on first boot the image runs a socket-only server for initdb, so a
	@# socket probe says "ready" while the published port still refuses connections.
	@echo "waiting for postgres…" && \
	  until docker compose exec -T db pg_isready -U balise -h 127.0.0.1 -q; do sleep 1; done

down: ## Stop the infrastructure
	docker compose down

logs: ## Follow the infrastructure logs
	docker compose logs -f --tail=100

db-shell: ## psql into the dev database
	docker compose exec db psql -U balise -d balise

# --- schema and data --------------------------------------------------------
migrate: ## Apply migrations (alembic upgrade head)
	cd api && uv run alembic upgrade head

migration-roundtrip: ## Upgrade → downgrade → upgrade on the *test* database, schema asserted
	BALISE_TEST_DATABASE_URL=$(TEST_DB) uv run python ops/scripts/migration_roundtrip.py
	cd api && DATABASE_URL=$(TEST_DB) uv run alembic check

migration: ## Autogenerate a migration: make migration m="add …"
	cd api && uv run alembic revision --autogenerate -m "$(m)"

seed: ## Load the checked-in Morbihan fixture (no network needed)
	uv run balise-ingest seed

fixture: ## Regenerate the Morbihan seed fixture from the live sources (review the diff!)
	uv run python -m balise_ingest.make_fixture --bbox=$(BBOX)

webdata: ## Rebuild data/ — the whole-Bretagne extract the Streamlit app reads (~5 min, network)
	uv run python -m balise_ingest.make_fixture \
	  --name bretagne --bbox=$(WEB_BBOX) --no-caps --out build/bretagne.geojson
	uv run python -m balise_ingest.webdata --extract build/bretagne.geojson --out data
	uv run python -m balise_ingest.places --bbox=$(WEB_BBOX) --out data

ingest-shom: ## SHOM balisage + ports + réglementation for BBOX
	uv run balise-ingest shom balisage --bbox=$(BBOX)
	uv run balise-ingest shom ports --bbox=$(BBOX)
	uv run balise-ingest shom reglementation --bbox=$(BBOX)

ingest-osm: ## OSM seamarks for BBOX via Overpass
	uv run balise-ingest osm delta --bbox=$(BBOX)

ingest-zmel: ## One ZMEL département: make ingest-zmel DEPT=56
	uv run balise-ingest datagouv zmel --dept $(DEPT)

ingest-tides: ## Precompute 7 days of tide predictions (needs SHOM_TIDE_API_KEY)
	uv run balise-ingest tides

ingest-weather: ## Refresh wind and wave forecasts (Open-Meteo, no key)
	uv run balise-ingest weather

ingest-all: ## Whole-France referential: SHOM layers, OSM bulk, tide ports (~30 min)
	uv run balise-ingest shom balisage
	uv run balise-ingest shom ports
	uv run balise-ingest shom reglementation
	uv run balise-ingest shom spm
	uv run balise-ingest osm full
	$(MAKE) ingest-weather

conflate: ## Explain the conflation of one object: make conflate EXPLAIN=spot_18421
	uv run balise-ingest conflate $(if $(EXPLAIN),--explain $(EXPLAIN),)

audit: ## Data-quality audit (docs/13)
	uv run balise-audit run

admin: ## Admin CLI help (feeds, suppression, GDPR)
	uv run balise-admin --help

mbfs: ## MBFS draft validator — the business-development artefact (docs/06 §A/S6)
	uv run balise-mbfs --help

# --- services ---------------------------------------------------------------
api: ## Run the API with reload on :8000
	uv run uvicorn balise_api.main:app --reload --port 8000

web: ## Run the web app on :5173
	$(WEB) dev

streamlit: ## The map app on the checked-in Bretagne extract, no db and no api (:8501)
	uv run streamlit run streamlit_app.py

workers: ## Run the v1 env worker (tides, weather)
	uv run balise-env-worker run

worker-once: ## One pass of the v1 environment jobs
	uv run balise-env-worker once

status-worker: ## 🔌 v2 — the availability decay worker (docs/06 §B)
	uv run balise-status-worker run

ais: ## 🔌 v2 — the AIS listener (needs FEATURE_AIS and AISSTREAM_API_KEY)
	uv run balise-ais-listener run

# --- tests ------------------------------------------------------------------
test: test-api test-ingest test-workers test-web ## The v1 gate (docs/13)

test-v1: test ## Alias: the v1 gate

test-v2: ## 🔌 The availability plug-in suite (docs/06 §B) — not part of the v1 gate
	FEATURE_AVAILABILITY=true BALISE_TEST_DATABASE_URL=$(TEST_DB) \
	  uv run pytest api/tests/v2 workers/tests/v2 -q

seam: ## The three seam tests that keep pluggability real (docs/13)
	BALISE_TEST_DATABASE_URL=$(TEST_DB) uv run pytest api/tests/test_availability_seam.py -q

test-api: ## API tests (unit + PostGIS integration + property tests)
	BALISE_TEST_DATABASE_URL=$(TEST_DB) uv run pytest api/tests -q

test-ingest: ## Ingest tests (golden files + conflation against PostGIS)
	BALISE_TEST_DATABASE_URL=$(TEST_DB) uv run pytest ingest/tests -q

test-workers: ## Worker tests (decay, stale feeds)
	BALISE_TEST_DATABASE_URL=$(TEST_DB) uv run pytest workers/tests -q

test-web: ## Frontend unit tests
	$(WEB) test

e2e-install: ## Install the Playwright browser
	$(WEB) exec playwright install --with-deps chromium

e2e: ## The five journeys, including the offline one (needs a seeded stack)
	$(WEB) build && $(WEB) e2e

# --- quality ----------------------------------------------------------------
fmt: ## Format Python and web sources
	uv run ruff format .
	$(WEB) fmt

fmt-check: ## CI gate: formatting, both stacks
	uv run ruff format --check .
	$(WEB) fmt:check

lint: ## CI gate: lint + types, both stacks
	uv run ruff check .
	uv run mypy api ingest workers ops app streamlit_app.py
	$(WEB) lint
	$(WEB) typecheck

typecheck: ## Types only
	uv run mypy api ingest workers ops app streamlit_app.py
	$(WEB) typecheck

check: fmt-check lint test ## Run before every commit

# --- build and ops ----------------------------------------------------------
build-web: ## Production web bundle + service worker
	$(WEB) build

prerender: build-web ## Prerender the /port/{slug} pages and the sitemap (needs the API up)
	cd web && node scripts/prerender.mjs

openapi: ## Dump the OpenAPI schema
	uv run python -c "import json;from balise_api.main import app;print(json.dumps(app.openapi(), ensure_ascii=False, indent=2))"

gen-api: ## Regenerate the frontend API types from the running API
	$(WEB) gen:api

tiles-flush: ## Drop the Redis tile cache (stale ETags after an ingest)
	uv run balise-admin tiles-flush

tiles-bench: ## Measure MVT generation time per layer and zoom (budget: p95 < 300 ms, ADR-0002)
	@for layer in spots navaids anchorages; do \
	  uv run python ops/scripts/tiles_bench.py --layer $$layer || exit 1; \
	done

clean: ## Remove build artefacts and caches
	rm -rf web/dist web/dev-dist .pytest_cache .mypy_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
