# ADR-0003 — Append-only observations with derived status

**Status:** Accepted — 2026-08-06. **Schema created in v1, writers implemented in v2**
([06 §A/S1](../06-availability-strategy.md)).

## Context

Availability comes from heterogeneous, unreliable, sometimes conflicting signals (port feeds,
community reports, AIS). The rule that turns them into a displayed state — decay half-lives, trust
weights, reputation — **will be wrong at first and tuned repeatedly**. We also need an audit trail:
if a sailor complains that the app said "free", we must be able to show exactly what was known and
when ([04 §3](../04-licensing-and-legal.md)).

## Decision

`observation` is append-only and immutable (only a `suppressed` flag may flip). `spot_status` is a
derived, recomputable projection — a cache, not a source of truth. Any status can be re-derived from
observations at any past instant.

## Consequences

- Tuning the derivation rule is safe: replay historical observations, compare the resulting status
  timeline against ground-truth audits, then deploy.
- Abuse handling is safe: suppress a contributor's observations and recompute; nothing is lost and
  no state is corrupted.
- Full auditability: every displayed state links to the observation that produced it.
- Cost: write volume and storage grow monotonically. Mitigated by monthly partitioning of
  `observation` past 50 M rows and by aggregating rows older than 12 months into statistics
  (which is also the GDPR retention boundary).
- The derivation function must be **pure** (`(spot, observations, now) → status`) so it is unit- and
  property-testable without a database. This is a hard constraint on `services/status.py`.

## Alternatives rejected

| Option | Why not |
|---|---|
| Mutable `spot.state` column updated in place | No audit trail, no replay, no safe rule tuning — and a bug silently rewrites history |
| Event sourcing the whole domain | Overkill; only availability has this property. The referential is fine as mutable rows with provenance |
| Time-series database (Timescale/Influx) for observations | Volume does not justify a second datastore; PostGIS + partitioning is enough, and we need joins to spatial data |
