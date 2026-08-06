# 15 — Risks & open questions

## Risks, ranked by expected damage

> **Deferring availability to v2 ([ADR-0005](adr/0005-availability-as-a-plugin.md)) retired the two
> biggest risks of the original plan.** R1 and R2 below are now *v2 gate criteria* rather than
> launch risks — which is most of the value of the decision. The live v1 risks are R3–R7 and R11.

### R1 — Layer B never materialises (was critical → now **not a v1 risk**)

Availability data has no public source. If no harbour ever sends a feed, availability never ships.

*Why it no longer threatens the product*: v1 does not promise it. The referential is the product; M3
is gated on ≥ 2 committed harbours + measured user demand ([14](14-roadmap.md)). "It never happens"
is now an acceptable outcome, not a failure.
*Residual*: the differentiator versus Navily (R4) then rests entirely on being free, open and
chart-complete. Watch that, not the feed count.

### R2 — Wrong "free" destroys trust (critical, but **deferred with the feature**)

One sailor diverted 5 NM to an occupied buoy at dusk tells the whole pontoon.

*v1 exposure: zero* — we show no state at all.
*v2 mitigations*: asymmetric decay (free decays far faster than occupied); confidence buckets;
source + age always visible; `unknown` as an honourable state; ground-truth audit as the M3 exit
gate, with rollback to the null provider as a one-line change if precision < 85 %.

### R3 — Liability after an incident (high, low probability)

A grounding or a broken mooring, with our app on the chart table.

*Mitigations*: [04 §3](04-licensing-and-legal.md) in full — disclaimer, no "safe" claims, no
depth without an estimate flag, no mooring-condition claims, CGU, RC pro insurance before launch,
legal review at M3.

### R4 — Competitive incumbency (Navily) (high, likely) — **now the top v1 risk**

Navily has 1.2 M users, ~18 000 moorings, ~100 partner French ports and booking. We arrive later,
and v1 arrives without the one thing they do not have (live occupancy).

*Mitigations*: differentiate v1 on (a) **free and open**, including open data out; (b) **the full
official referential** — SHOM nav aids, anchorage restrictions, submarine cables, regulatory limits.
Navily is community-first; we are chart-first, and no competitor offers the SHOM layer in a free
consumer app; (c) nav aid explainer pages, a use case (P5) Navily does not serve at all; (d) later,
live occupancy + an open feed spec vendors implement once, versus their proprietary integrations.
**Do not compete on community reviews and photos — we lose that fight**, which is also why they are
out of v1 scope ([00](00-vision-and-scope.md)).
*Watch*: if v1 cannot show a clear "why not just use Navily" answer in user interviews by M2, the
positioning is wrong and pulling M3 forward will not save it.

### R5 — Upstream data breaks silently (medium, likely)

A SHOM schema change or an OSM tagging shift empties a layer.

*Mitigations*: count-anomaly gates (> 20 % blocks promotion), golden-file parser tests, never delete
on absence, raw snapshots for 90 days, `/health/data`.

### R6 — ODbL contamination of our availability data (medium, low)

Sloppy schema design could make observations a Derivative Database of OSM.

*Mitigations*: [04 §2](04-licensing-and-legal.md) — physical separation by provenance, per-attribute
provenance, quarterly ODbL extract published. Get this reviewed by a lawyer once, early.

### R7 — Seasonality (medium, certain)

80 % of usage in 8 weeks. Cold data, cold community and cold infra for 10 months.

*Mitigations*: CDN-heavy architecture that costs little at rest; off-season content strategy (nav aid
explainers, SEO, port pages); winter is for data-quality work and partner onboarding.

### R8 — Community abuse (low-medium, moderate) — **v2 only**

Locals reporting "occupied" everywhere to keep visitors away; a competitor poisoning the data.

*v1 exposure*: limited to `/issues` (referential corrections), which are human-moderated before they
land in `overrides.yml` — low volume, high friction, low payoff for an abuser.
*v2 mitigations*: reputation weighting, shadow-weighting rather than visible bans, plausibility gate
on position, spike detector per device and per zone, append-only observations so any recompute is
safe.

### R9 — GDPR complaint over geolocation (low, moderate)

*Mitigations*: [04 §4](04-licensing-and-legal.md) — no raw GPS stored, snapping to spots, short
retention, self-service export/erase, CNIL register from day one.

### R11 — The seam rots, or becomes a second product (medium, likely) — **new**

Two opposite failure modes of "keep it pluggable":

1. **Rot** — nobody exercises the seam for 18 months; when M3 starts, the provider port no longer
   matches reality and the "one-line swap" is a rewrite. The seam bought nothing.
2. **Gold-plating** — the seam quietly grows into a half-built availability system: speculative
   abstractions, unused config, dead branches, a `feed` admin UI "while we're at it". v1 pays the
   cost of v2 and gets none of the benefit.

*Mitigations*: a hard **≤ 1 engineer-day budget** for all six seams; the seam test running on every
build; `FEATURE_AVAILABILITY` referenced exactly once, CI-enforced; a test asserting the availability
tables stay empty ([13](13-testing-and-quality.md)); and an explicit escape hatch — **if preserving
the seam ever costs more than a day, drop it and accept the later migration**
([ADR-0005](adr/0005-availability-as-a-plugin.md)).
*Review trigger*: any PR that adds a second reference to the flag, or writes to a 🔌 table, is
rejected on sight.

### R10 — Two-engineer team, three-domain product (medium, certain)

Marine data, real-time systems and a field-usable mobile UI is a lot of surface.

*Mitigations*: the "deliberately absent" list in [07](07-architecture.md) — no Kafka, no k8s, no
microservices, no tile server, no chart library. Postgres does the tiles, the queue and the pub/sub
trigger.

## Open questions (owner + deadline needed)

| # | Question | Blocks | Decide by |
|---|---|---|---|
| Q1 | Do SHOM tide API terms allow us to cache and serve predictions? If not, offline tides need in-house harmonic computation. | Offline tides | M1 start |
| Q2 | Will any harbour-software vendor implement MBFS, or must we integrate port by port? | M3 gate (not v1) | M2 end |
| Q3 | Business model — free forever, port subscriptions, booking commission, or association/subsidy? Affects the licence we publish under and whether SHOM/collectivité grants are available. | Legal structure | M1 end |
| Q4 | Legal structure: association loi 1901 (grants, goodwill, OSM-friendly) vs SAS (investment, booking revenue)? | Contracts, insurance | M1 end |
| Q5 | Which 5 départements' ZMEL datasets are usable as-is? Needs a hands-on review of each file. | M1 scope | M1 week 2 |
| Q6 | Do we host our own base-map tiles (PMTiles) or use a provider? Cost vs control at seasonal peak. | M1 infra | M1 week 3 |
| Q7 | Do we accept anonymous check-ins forever, or require an account after N reports? Friction vs abuse. | M3 design | M3 start |
| Q11 | What replaces availability as the v1 hook in the launch narrative — "la carte SHOM gratuite", "toutes les bouées de France", or the nav aid explainers? Decides the SEO and press angle. | M1 launch comms | M1 week 4 |
| Q8 | Domain and trademark: is `balise.fr` available, and does the name conflict at INPI? | Branding | M1 end |
| Q9 | Is `morfac` + ZMEL enough for mooring coverage, or must we survey fields ourselves (photo + GPS walk-around by contributors)? | M2 scope | M1 end |
| Q10 | DOM-TOM: same product or a separate launch? Data exists; community does not. | Post-M3 | M3 |

## Assumptions stated explicitly

0. **v1 has no availability** and is a complete product without it
   ([ADR-0005](adr/0005-availability-as-a-plugin.md)). Everything below assumes that scope.
1. French metropolitan coast only at launch; DOM-TOM data ingested but not promoted.
2. Web-only per the brief — a PWA, no native apps, accepting that iOS PWA background geolocation is
   limited (implicit check-out on geofence exit is therefore best-effort on iOS).
3. No booking, no payment, no money movement in v1 — which keeps us out of PSP/regulatory scope.
4. Two engineers, part-time BD; anything requiring a 5-person team is out of the plan.
5. SHOM open data remains free under Etalab v2 (it has been for years; if it changed, R5 applies).
