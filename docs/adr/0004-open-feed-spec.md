# ADR-0004 — Publish MBFS, an open GBFS-like feed spec

**Status:** Accepted — 2026-08-06. **Drafted in v1 (`docs/mbfs/`), published when the first partner
commits** ([06 §A/S6](../06-availability-strategy.md)). A public spec with zero implementers is a
maintenance liability; in v1 its job is to be the artefact we put in front of capitaineries.

## Context

Berth occupancy exists today — inside harbour management software, fed by IoT sensors (e.g.
Nauticspot's pontoon sensors and connected mooring buoys, deployed in ports including Ajaccio
Charles-Ornano). None of it is publicly exposed. There are ~470 marinas in France and a handful of
software vendors serving them. Integrating port by port, bespoke, does not scale with two engineers.

Bike-sharing solved the identical problem with **GBFS**: one open spec, implemented once per vendor,
consumed by every app — which is why every city bike system is visible in every mapping app.

## Decision

Publish **MBFS (Mooring & Berth Feed Specification)**, deliberately GBFS-shaped: a versioned JSON
document with `last_updated` / `ttl` / `data`, supporting both pull (we poll a URL) and push (they
POST deltas or a snapshot). Spec and a reference implementation + validator are MIT-licensed and
public at `/opendata/mbfs`. Field-level aggregate counts (`num_free`) are a **valid minimum**
payload — per-berth detail is optional.

## Consequences

- One vendor integration unlocks all their ports at once. This is the only path to national coverage.
- The minimum payload removes the two objections capitaineries actually raise: "I don't want to
  expose my customers' data" and "my system can't do that".
- Publishing the spec openly means a competitor can consume the same feeds. Accepted deliberately:
  the network effect of vendors implementing *one* standard is worth more to us than exclusivity we
  cannot enforce anyway, and it makes ports far more willing to sign.
- Obligations on us: version the spec, keep the validator working, never break a live feed. A spec
  is a long-term commitment, not a document.
- Feed staleness must degrade to `unknown`, never to a stale state — a dead feed that keeps showing
  green would discredit both us and the port.

## Alternatives rejected

| Option | Why not |
|---|---|
| Bespoke integration per port | Does not scale; every port becomes a maintenance burden |
| Scraping port websites | Brittle, legally grey, adversarial towards the exact partners we need |
| Private API, contract-only | Ports and vendors have no incentive to build for a single small consumer |
| Adopt GBFS verbatim | Vocabulary mismatch (stations/bikes vs fields/spots) and no notion of draught, LOA or tide constraints |
