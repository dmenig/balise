# ADR-0005 — Availability is out of v1, behind a provider seam

**Status:** Accepted — 2026-08-06. Supersedes the v1 scope in ADR-0003 and ADR-0004.

## Context

The original scope had live availability ("which mooring is free") in v1. Three facts made that
untenable as a *v1* commitment:

1. **No public data source exists in France** ([03 §F](../03-data-sources.md)). Occupancy lives inside
   capitainerie software. Obtaining it is a partnership problem measured in months of calendar time,
   not an engineering problem.
2. **An empty or wrong availability layer is worse than none.** It trains users to ignore the exact
   signal we would later want them to trust, and a wrong "free" at dusk is the failure mode most
   likely to lose a user permanently.
3. The referential is a complete, shippable product on its own, and shipping it is what earns the
   credibility that makes step 1 possible.

But availability remains the long-term differentiator, so v1 must not make it expensive to add.

## Decision

**v1 ships no availability.** Availability is a **plug-in**, defined by six seams
([06 §A](../06-availability-strategy.md)) built in v1 under a hard budget of **≤ 1 engineer-day**:

| Seam | v1 obligation |
|---|---|
| S1 schema | Availability tables created empty; read path already `LEFT JOIN spot_status` |
| S2 domain | One `AvailabilityProvider` port; `NullAvailabilityProvider` wired in `main.py` |
| S3 API | `status` present and `null` everywhere; availability routes specified, returning `501` |
| S4 tiles | Status never in tiles (already ADR-0002) — nothing to change later |
| S5 UI | Paint expressions in final form, neutral fallback; every component handles `status: null` |
| S6 spec | MBFS drafted in-repo, unpublished; used as a business-development artefact |

Two rules make the seam real rather than decorative:

- **`FEATURE_AVAILABILITY` is referenced exactly once** in the codebase (CI-enforced). No other file
  knows availability exists.
- **A CI seam test wires a fake provider** and asserts a status reaches the API response. If it needs
  more than swapping the provider, the seam has rotted and is fixed in that PR.

Switching availability on is then: implement the v2 module, replace one object, flip one flag.

## Consequences

- v1 is dramatically simpler and more cacheable: no observations, no decay worker, no reputation, no
  websocket, no moderation of state, no AIS. It is close to a static site with a search API
  ([07](../07-architecture.md)).
- The v1 answer to "is it free?" is the capitainerie's phone number and VHF channel, one tap away.
  Honest, and it is what sailors do today anyway.
- Availability becomes **demand-gated**: M3 starts only when ≥ 2 harbours commit to send data *and*
  users ask for it ([14](../14-roadmap.md)). It may never start, and that is an acceptable outcome.
- We keep the option at low cost, and we keep the *rollback* at low cost too — if the M3 pilot
  measures "free" precision below 85 %, reverting to the null provider is one line.
- Cost: six empty tables, a `null` field, some `501` routes, and a discipline that must be held for
  the whole life of v1. Cheap, but not free — the discipline is the expensive part, which is why the
  two enforcement rules above are CI checks and not conventions.

## Alternatives rejected

| Option | Why not |
|---|---|
| Keep availability in v1 | Blocks launch on partnerships we do not control; risks shipping an empty layer |
| Ship availability as community-only in v1 | Cold-start guarantees sparse, low-confidence data — the "wrong free" failure mode, at launch, with no port feed to anchor quality |
| Drop availability entirely, no seams | Saves ~1 day now, costs a schema migration on a live map, a tile-format change and a UI redesign later. Bad trade |
| Build the full v2 design behind a flag in v1 | Weeks of untested, unexercised code that will be rewritten once real feed data arrives. Speculative generality — the seam is the minimum that preserves the option |
| Fake/estimate availability at launch | Fatal to trust in a small, vocal community ([06 §B.3](../06-availability-strategy.md)) |
