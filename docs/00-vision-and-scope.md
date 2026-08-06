# 00 — Vision & scope

## Problem

A sailor arriving at an unknown French harbour at 18:00 has three questions and no good answer to
any of them:

1. **Where can I stop?** Which mooring buoys, visitor berths and legal anchorages exist here?
2. **Is anything free right now?** Today this means calling the capitainerie on VHF ch. 9 during
   office hours, or entering the harbour and looking.
3. **Is it right for my boat?** Draught, max LOA, holding, exposure to tonight's wind, tide.

Existing apps (Navily, Nauticspot's plaisancier app, port-specific booking sites) each solve a slice:
Navily is a community guide + booking with ~100 partner ports in France; Nauticspot sells berth
sensors to harbours. **Nobody offers a single free map of every French mooring and berth with a live
free/occupied state.** That is the gap.

## Product statement

> **Balise** — a free French web app (PWA) that maps every navigation mark, mooring buoy, anchorage
> and visitor berth on the French coast, with everything needed to choose tonight's stop: depth,
> size limits, shelter, price, contacts, tide.

**v1 answers questions 1 and 3. Question 2 — "is anything free right now" — is deliberately out of
v1** ([06](06-availability-strategy.md)): it has no public data source and can only be manufactured
through partnerships that take months. v1 answers it the honest way instead: the capitainerie's
phone number and VHF channel, one tap away, on every sheet.

The long-term ambition stays "Google Maps for the seaward side, Vélib' for the mooring" — v1 is the
map half, built so the Vélib' half plugs in without rework.

## Principles

1. **Useful before it is live.** The static referential alone (marks, buoys, marinas, anchorages,
   depths, contacts, VHF channels, prices) is already worth using. Availability is an increment,
   never a prerequisite — hence v1.
2. **Honest confidence.** Never show "free" when we mean "free 4 hours ago, reported by one person".
   A wrong "free" costs a sailor an hour of daylight. In v1 this principle is applied in its
   strongest form: **we show no availability at all rather than a bad one.**
3. **Not a navigation instrument.** We are a planning aid. Official up-to-date charts remain
   mandatory (see [04](04-licensing-and-legal.md)).
4. **French coast first, whole coast.** Manche/Mer du Nord, Atlantique, Méditerranée, Corse. DOM-TOM
   are in the data but out of the launch scope.
5. **Open data in, open data out.** We consume ODbL/Etalab data; we publish our referential back
   under the same terms. Cost of goodwill is low, value with capitaineries and OSM is high.
6. **Offline-first.** Phone signal dies 2 NM offshore. What you looked at must still be there.

## In scope (v1, web only)

- Map of the French coast with: navigation marks, mooring buoys, anchorage zones, marinas.
- Spot detail sheet: type, depth, max LOA/draught, holding, exposure, operator, price, VHF, phone.
- Harbour sheet with contacts, services, opening hours, prices — and a one-tap call button.
- Filters: buoy vs berth vs anchorage, min depth, max LOA/draught, shelter from a given wind sector.
- Search by port name, commune, or coordinates.
- Nav aid explainer pages: what this mark means, in plain French.
- Tides for the nearest reference port, incl. depth at tonight's low water; wind/wave 48 h.
- Offline: last-viewed area cached, read-only, explicit "download this area".
- User-reported **data corrections** (wrong position, buoy removed, wrong price) → moderation queue.
- French UI (`fr-FR`), i18n-ready for `en`.
- **The six availability seams** ([06 §A](06-availability-strategy.md)) — schema, provider port, API
  field, tile format, neutral UI states, MBFS draft. Budget: ≤ 1 engineer-day.

## Out of scope (v1) — deliberate

| Excluded | Why |
|---|---|
| **Live availability (free/occupied)** | **No public data source; needs partnerships that take months. Deferred to M3 and demand-gated — [06](06-availability-strategy.md), [14](14-roadmap.md)** |
| Community check-in / check-out | Part of availability; also needs moderation and anti-abuse machinery |
| Partner harbour feeds (MBFS) | Spec drafted as a BD artefact, not implemented |
| Photos & reviews | Moderation cost; Navily already owns this ground ([15 R4](15-risks-and-open-questions.md)) |
| Native iOS/Android apps | Web only per brief; PWA covers install + offline |
| Booking & payment | Requires contracts with each port; only after availability is trusted |
| Routing / autopilot / chart plotting | Regulated, liability-heavy, not our value |
| Official raster charts (SHOM scans) | Licence cost; OSM + OpenSeaMap base is enough for planning |
| DOM-TOM launch | Data exists, but partner and community density is zero |
| Commercial ports / cargo berths | Different users, different regulation |
| AIS | Only ever an availability signal ([06 §B.1](06-availability-strategy.md)) |

## Success criteria for v1

| Metric | Target at launch + 6 months |
|---|---|
| Referential coverage | ≥ 95 % of French marinas, 100 % of SHOM nav aids, ≥ 80 % of known ZMEL |
| Position accuracy (audited sample) | ≥ 90 % of moorings within 25 m of truth |
| Weekly active sailors in season | 5 000 |
| Harbours claimed by their operator | ≥ 20 |
| Data corrections submitted & merged | ≥ 100 / season |
| Seam cost | ≤ 1 engineer-day, seam test green on every build |

Availability metrics (feed count, report volume, "free" precision ≥ 85 %) move to the **M3 exit
criteria** ([14](14-roadmap.md)) and are explicitly *not* v1 targets.
