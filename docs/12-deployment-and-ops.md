# 12 — Deployment & operations

## Hosting principles

- **EU-hosted** (GDPR, [04 §4](04-licensing-and-legal.md)). Scaleway (Paris), OVH, or Clever Cloud.
- Boring and cheap: one VM (or a managed container service) + a managed Postgres + a CDN. No
  Kubernetes until there is a measured reason.
- Seasonal traffic: capacity must be trivially scalable for July–August and shrinkable in winter.

## Topology (prod)

```
Cloudflare (CDN, TLS, WAF, cache for /tiles and static)
        │
   ┌────▼──────────────┐
   │ app VM (4 vCPU)   │  docker compose: api ×2, env-worker, caddy
   └────┬──────────────┘        🔌 v2 adds: status-worker, ais-listener
        │
   ┌────▼──────────────┐        ┌──────────────────┐
   │ Managed Postgres  │        │ Object storage   │
   │ 16 + PostGIS      │        │ (photos, raw     │
   │ + read replica    │        │  snapshots)      │
   └───────────────────┘        └──────────────────┘
   ┌───────────────────┐
   │ Managed Redis     │
   └───────────────────┘
```

`web` is a static bundle on the CDN (plus prerendered `/port/{slug}` pages). `ingest` runs as a
scheduled job (cron on the app VM in v1; move to a scheduler when jobs exceed ~15 min).

## Estimated monthly cost (v1, launch scale)

| Item | ~€/month |
|---|---|
| App VM (4 vCPU / 8 GB) | 40 |
| Managed Postgres (2 vCPU / 8 GB / 100 GB) | 70 |
| Managed Redis (1 GB) | 15 |
| Object storage + egress | 10 |
| CDN (Cloudflare Pro or free tier) | 0–20 |
| Domain, mail, monitoring | 20 |
| **Total** | **~€155–175** |

Tiles on the CDN are what keeps this flat under a seasonal traffic spike. Without CDN caching of
`/tiles`, the VM cost triples in August.

## Deployment pipeline

```
push to main → CI (lint, type, tests, e2e) → build images (api, workers) + web bundle
             → push to registry → deploy to staging → smoke tests
             → manual approval → deploy to prod (rolling, api ×2 behind Caddy)
             → post-deploy checks: /health, tile render, one known spot status
```

- Migrations run **before** the new image is served, and must be backward-compatible with the
  previous release (expand/contract: add column → deploy → backfill → drop in a later release).
- Images tagged with the git sha; rollback = redeploy previous tag. DB rollback is never automatic.

## Health & readiness

| Endpoint | Checks |
|---|---|
| `GET /health` | process alive |
| `GET /ready` | DB reachable, Redis reachable, `ref_version` present |
| `GET /health/data` | last successful ingest per source, feed staleness, count anomalies |

## Monitoring

| Signal | Tool | Alert |
|---|---|---|
| Latency p95 per route, error rate | OpenTelemetry → Grafana/Tempo | p95 `/spots` > 500 ms for 10 min |
| Tile render time | histogram per zoom | p95 > 300 ms |
| Ingest job outcome | job metric + log | any failure, or count delta > 20 % |
| CDN hit ratio on `/tiles` | provider metric | < 90 % (v1 should sit above 95 %) |
| 🔌 Feed staleness (v2) | gauge per feed | feed silent > 3 × ttl → page the partner-facing alias |
| 🔌 Websocket connections (v2) | gauge | > 80 % of cap |
| DB | managed provider metrics | connections > 80 %, disk > 75 % |
| Frontend | Sentry (errors), web-vitals beacon | LCP p75 > 3 s |
| Uptime | external prober on `/ready` and on the map page | 2 consecutive failures |

**Data-quality alerts matter more than infra alerts here.** A silently stale feed showing green pins
is worse than a 500.

## Backups & DR

| Asset | Policy |
|---|---|
| Postgres | Managed daily snapshot + PITR 7 days; monthly restore drill (documented, timed) |
| Raw source snapshots | Object storage, 90 days — the referential is fully rebuildable from these |
| Photos | Versioned bucket, 30-day soft delete |
| Secrets | Provider secret manager; no secrets in git; rotation documented |

RPO 24 h for the referential (rebuildable), 15 min for observations (PITR). RTO 4 h.

## Runbooks

Kept in `ops/runbooks/`. **v1 runbooks:**

1. **Wrong data reported by a user** (buoy in the wrong place) → `--explain` the conflation, add an
   entry to `overrides.yml`, re-run conflate, PR.
2. **Upstream schema change (SHOM/OSM)** → job already failed and kept old data; update the mapping,
   add a regression fixture, redeploy.
3. **Traffic spike** → scale api replicas, verify CDN hit ratio on `/tiles`, extend list-response
   TTL.
4. **GDPR erasure request** → `balise-admin gdpr erase --email` (deletes account, anonymises
   contributions) with a written trace.
5. **Ingest wiped or corrupted the referential** → roll back to the previous `ref_version`, re-load
   from the raw snapshot in object storage, then investigate.

**🔌 v2 runbooks** (written when M3 starts):

6. **A partner feed went stale** → check `/feeds/{id}/health`, confirm with the port, force the feed
   to `unknown` (`balise-admin feed disable <id>`), notify.
7. **Abuse / report poisoning** → quarantine device hashes, `balise-admin observations suppress
   --contributor <id>`, recompute affected statuses (append-only design makes this safe).
8. **Availability quality collapse** → `FEATURE_AVAILABILITY=false`, redeploy. The app reverts to
   v1 behaviour (`status: null` everywhere) with no data loss and no client breakage. **This
   rollback must be verified in staging before M3 ships**, not first attempted in an incident.

## Security baseline

- TLS everywhere, HSTS, CSP without `unsafe-inline`, `SameSite` cookies, CSRF on cookie-auth routes.
- Rate limits at the CDN and in the app.
- Feed tokens hashed at rest, scoped, rotatable, never logged.
- Photo uploads: type sniffing, size cap, EXIF strip, served from a separate origin.
- Dependency scanning (`pip-audit`, `pnpm audit`) in CI; weekly base-image rebuild.
- No PII in logs; IPs truncated ([04 §4](04-licensing-and-legal.md)).


---

## Streamlit Community Cloud (the public map app)

Entrypoint `streamlit_app.py`, branch `main`, no secrets, no backend. It cost five rounds of
blind debugging to get right, so the traps are written down.

**The dependency file is the one that bites.** Cloud picks *one* file and prefers a lockfile to
`requirements.txt`. This repo ships `uv.lock` at the root, and that lockfile covers the monorepo
workspace — `balise-api`, `balise-ingest`, `balise-workers` — with **no streamlit, pydeck, pandas
or pyarrow in it**. A build resolving it installs the API stack and then runs the app against
whatever streamlit the platform ships. Every layout rule keys off internal DOM hooks
(`.st-key-*`, `data-testid=…`), so a different release drops the page back into document flow:
chrome unstyled, night mode inert, search box unusable — and `requirements.txt` pins do nothing
because they are never read. The root `pyproject.toml` therefore declares the four app
dependencies alongside the workspace members; **keep it and `requirements.txt` in step**.

**Pin, do not floor, `streamlit` and `pydeck`.** The layout depends on undocumented DOM, and
pydeck decides which arguments become `@@=` accessor expressions.

**Do not assume the host serves `static/`.** A host can register Streamlit's static route
internally and still not expose it through its edge, which returns 200 to anything the server
probes and HTML to the browser. The map then draws an empty basemap and reports nothing. The app
carries its data in the deck spec for this reason; see the payload notes in the
[README](../README.md).

**Redeploying after a dependency change: delete the app and recreate it.** Reboot commonly reuses
the cached environment, which is exactly what you are trying to replace.

**`?debug=1`** renders the installed streamlit/pydeck/pandas versions, whether `.streamlit/config.toml`
was read, and the viewer's theme — one screenshot answers what a remote host is doing.

Verify a change the way Cloud will build it, not the way your dev shell does:

```bash
git clone --depth 1 <repo> /tmp/clean && cd /tmp/clean
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run streamlit_app.py
```
