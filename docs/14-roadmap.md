# 14 — Roadmap

Estimates assume **2 engineers** (1 backend/data, 1 frontend). Business development for partner
harbours runs in the background from M0 — it costs calendar time, not engineering time, and it is
what gates M3.

**v1 = the referential.** Availability is deferred and demand-gated ([06](06-availability-strategy.md)).

---

## M0 — Spike (2 weeks)

Prove the data before building anything.

- [ ] Ingest SHOM `balisage` + `achare` + `hrbfac` for one region (Morbihan) into PostGIS.
- [ ] Ingest OSM seamarks for the same bbox; run a first conflation and **eyeball 100 objects**.
- [ ] Static MapLibre page rendering nav aids + moorings from `ST_AsMVT`.
- [ ] Answer with evidence: *how many real mooring buoys do we actually know about in one bay, and
      are the positions good enough to trust?*
- [ ] Show the MBFS draft ([06 §B.4](06-availability-strategy.md)) to 3 capitaineries and 1
      harbour-software vendor. **This is information gathering, not a commitment** — the answers
      calibrate M3, they do not gate v1.

**Exit criteria:** ≥ 90 % of the moorings a local sailor knows in the pilot bay are present and
within 25 m of truth. If this fails, the whole product fails — stop and reconsider.

## M1 — v1: referential nationwide (7 weeks) → **public launch**

- [ ] All SHOM layers, France-wide, weekly job with count-anomaly guards.
- [ ] OSM bulk pipeline (`osmium`) + hourly deltas.
- [ ] ZMEL adapters for the 5 densest départements (56, 29, 22, 17, 83).
- [ ] Schema + Alembic — **including the empty availability tables** ([06 §A/S1](06-availability-strategy.md)).
- [ ] Tiles, `/spots`, `/harbours`, `/navaids`; `status: null` in every payload
      ([06 §A/S3](06-availability-strategy.md)); availability endpoints specified, returning `501`.
- [ ] `NullAvailabilityProvider` wired once in `main.py` + the seam test in CI
      ([06 §A](06-availability-strategy.md)).
- [ ] Web: map, filters (kind, depth, LOA, shelter), spot sheet, harbour page, search.
- [ ] Nav aid explainer pages (`/balise/{id}`) — the SEO engine.
- [ ] Tides for reference ports; depth-at-low-water computation.
- [ ] PWA shell + offline area download.
- [ ] Legal pages, attributions, permanent disclaimer strip.

**Exit criteria:** a sailor can plan a full Brittany-to-Med coastal trip with the app and find it
useful. Lighthouse ≥ 90. Offline journey green in CI. Seam test green.

**Positioning at launch: *« la carte des mouillages et des balises »*.** Say nothing about live
availability — not even "coming soon". Promising it before it exists is how the launch burns.

## M2 — Make the referential the best in France (6 weeks)

No new product surface. Depth and trust in what we already ship.

- [ ] ZMEL coverage extended to all coastal départements.
- [ ] Data-quality audit job nightly ([13](13-testing-and-quality.md)) + a public data-quality page.
- [ ] User-reported corrections (wrong position, buoy removed, wrong price) → moderation queue →
      `overrides.yml` PR. **This is a referential loop, not an availability loop** — it feeds
      geometry and attributes, never state.
- [ ] Harbour claim flow: a capitainerie edits its own contacts, prices, hours. Doubles as the
      relationship that makes M3 possible.
- [ ] Push corrections back to OSM; publish the ODbL extract ([04 §2](04-licensing-and-legal.md)).
- [ ] SEO, content, performance, accessibility pass.
- [ ] Legal review, CGU, RC pro insurance, CNIL register finalised.

**Exit criteria:** ≥ 95 % marina coverage, ≥ 80 % of known ZMEL, 5 000 weekly actives in season,
≥ 20 harbours claimed by their operator.

## M3 — Availability pilot (8 weeks) — **gated, not automatic**

Start only when **both** gates are met:

| Gate | Threshold |
|---|---|
| Supply | ≥ 2 harbours have committed in writing to send MBFS data |
| Demand | Availability is the top-3 request in user feedback, or ≥ 20 % of sessions hit the (absent) filter |

If the gates are not met, **do not build it** — spend the quarter on M2/M4 instead and re-evaluate
next season. Building it unasked is the single most expensive mistake available here.

When it starts, unwiring the seam ([06 §A](06-availability-strategy.md)) in order:

- [ ] Derivation service (pure function) + decay worker + `spot_status` projection.
- [ ] `RealAvailabilityProvider` replaces the null one — **one line in `main.py`**.
- [ ] MBFS v0.1 published + reference client + validator CLI; feed endpoints, tokens, health page.
- [ ] 3 pilot harbours live.
- [ ] Community check-in/out, offline queue, reputation, anti-abuse — enabled **only in pilot zones**.
- [ ] Websocket live updates + polling fallback.
- [ ] UI: status chips, confidence styling, source + age everywhere.
- [ ] Moderation console; ground-truth audit protocol running.

**Exit criteria:** "free" precision ≥ 85 % in pilot zones, measured by physical ground-truth audit
([13](13-testing-and-quality.md)). **If precision < 85 %, roll back to the null provider and ship
nothing.** The rollback must stay a one-line change for the entire life of M3 — that is what the
seam is for.

## M4 — Depth (ongoing, parallel to M2/M3)

- Météo-France GRIB for finer forecasts; swell/wind exposure scoring per spot.
- Bathymetry contours, tide curve improvements, offline tide tables.
- English UI for foreign crews; DOM-TOM referential.
- AIS tier (T3) and statistical priors (T4) — only after M3 proves the base case.
- Booking — only once ≥ 30 partner harbours exist and they ask for it.

---

## Sequencing rules

1. **Referential before availability. Always.** A great map with no live data is a product; a live
   map with a bad referential is a liability.
2. **Business development starts at M0, product work at M3.** Conversations take months; keeping the
   MBFS draft in front of ports costs nothing and produces the M3 gate signal.
3. **The seam stays cheap or it goes.** If preserving pluggability ever costs more than a day of v1
   work, drop the seam and accept a later migration ([06 §A](06-availability-strategy.md)).
4. **No booking before trust.** Taking money for a berth we wrongly said was free is a refund, a
   complaint and a bad review at once.
5. **Every milestone ships to production.** No dark builds.
