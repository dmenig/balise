# 06 — Availability (deferred to v2, kept pluggable)

**Decision: v1 ships with no availability at all.** No free/occupied state, no community check-in,
no partner feeds, no AIS. The v1 product is the referential ([00](00-vision-and-scope.md)).

**But the seams are built in v1**, so switching availability on later is wiring, not surgery. This
document has two parts: §A the seams we build now (binding on v1 code), §B the design we will
implement when it is switched on (blueprint, not v1 work).

## Why deferred

1. Availability has **no public source in France** ([03 §F](03-data-sources.md)). It cannot be
   fetched, only manufactured — through partnerships and community, both of which take calendar
   months and zero engineering.
2. A map with a `free/occupied` layer that is empty or wrong is **worse than no layer**: it trains
   users to ignore the signal exactly when we later make it good.
3. The referential is a complete product on its own. Shipping it first gets us users, SEO and — the
   thing that actually unblocks availability — credibility with capitaineries.

Availability is therefore a **demand-gated** feature: we build it when we have both (a) a partner
willing to send data and (b) users asking for it. See [14](14-roadmap.md) M3.

---

# §A — The seams (v1 scope, binding)

Six seams. Total v1 cost budgeted at **≤ 1 engineer-day**. If any seam starts costing more than
that, it is over-engineered — cut it and accept the later migration.

### S1 — Schema seam
The availability tables (`observation`, `spot_status`, `field_status`, `feed`, `contributor`) are
created by the **initial v1 migration** and stay empty ([05](05-domain-model.md)).

*Why create empty tables:* the read path already does `LEFT JOIN spot_status USING (spot_id)`, so
the query shape, the indexes and the FK cascades are settled and exercised from day 1. Six empty
tables cost nothing; retrofitting a join into a hot query on a live map costs a sprint.

### S2 — Domain seam
One port, one null implementation, wired once at app startup:

```python
class AvailabilityProvider(Protocol):
    def status_for(self, spot_ids: list[int]) -> dict[int, SpotStatus]: ...
    def field_status_for(self, field_ids: list[int]) -> dict[int, FieldStatus]: ...


class NullAvailabilityProvider:
    def status_for(self, spot_ids: list[int]) -> dict[int, SpotStatus]:
        return {}

    def field_status_for(self, field_ids: list[int]) -> dict[int, FieldStatus]:
        return {}
```

**Rule: no v1 code branches on availability anywhere except this wiring.** Not in routers, not in
serialisers, not in the frontend. A missing status is an ordinary empty-dict case, not a special
case. Any `if FEATURE_AVAILABILITY:` outside `main.py` is a review rejection.

### S3 — API seam
`status` is present in every spot payload and is **always `null` in v1** ([08](08-api-contract.md)):

```json
{"id": "spot_18421", "kind": "mooring_buoy", "status": null}
```

A client written against v1 keeps working unchanged in v2 — the field simply starts being populated.
Availability-specific query params (`state`, `min_confidence`) and endpoints (`/status`, `/reports`,
`/feeds/*`, `WS /stream`) are **specified now, not implemented**: they return
`501 availability_not_enabled` with a `problem+json` body. Specified-and-refusing beats undefined.

### S4 — Tile seam
Already guaranteed by [ADR-0002](adr/0002-tiles-from-postgis.md): status is never in tiles. Turning
availability on adds a separate `/status` call; the tile format, the cache policy and the ETag
strategy do not change. This is the seam that would have been most expensive to retrofit, and it
costs literally nothing to preserve.

### S5 — UI seam
MapLibre paint expressions read `feature-state.state` and fall back to the neutral style when unset
([09](09-frontend-and-map.md)). In v1 nothing calls `setFeatureState`, so every spot renders neutral.
Enabling availability = starting to call it. **No v1 pin design may depend on there being exactly
one state** — the legend, the cluster badge and the list row all have a neutral variant.

### S6 — Spec seam
MBFS (§B.4) is **drafted and kept in `docs/mbfs/`, not published**. Publishing a public spec with
zero implementers is a maintenance liability. The draft's real v1 job is as a business-development
artefact: it is what we put in front of a capitainerie or a software vendor to ask *"could you send
this?"* — and their answer is the M0/M1 exit signal.

### Anti-rot measure (this is the part that usually fails)

A seam nobody exercises decays silently. One CI test keeps it honest:

```python
def test_availability_seam_carries_status_to_the_api(client_with_fake_provider):
    # wires a FakeAvailabilityProvider returning one known status, nothing else changes
    body = client_with_fake_provider.get("/v1/spots?bbox=-3,47,-2,48").json()
    assert body["features"][0]["properties"]["status"] == {
        "state": "free",
        "confidence": 0.9,
        "as_of": "2026-08-06T13:41:30Z",
        "source_kind": "port_feed",
        "age_seconds": 0,
    }
```

If that test needs more than swapping the provider to pass, the seam has rotted — fix it in that PR.
It runs on every build for the whole life of v1.

---

# §B — The v2 design (blueprint, not v1 work)

Retained in full so the seam decisions above are traceable to a real design.

## B.1 Signal tiers

| Tier | Signal | Coverage | Latency | Base trust |
|---|---|---|---|---|
| **T1** | Partner harbour feed (harbour software / IoT berth sensors, e.g. Nauticspot-style pontoon sensors) | Whole marina, exact | seconds–minutes | 0.95 |
| **T2** | Community check-in / check-out | Anywhere, sparse | minutes | 0.55 → 0.85 with reputation |
| **T3** | AIS at rest (`aisstream.io`) | Boats > ~15 m only | 1–5 min | 0.5 (hint) |
| **T4** | Statistical prior (season, weekday, weather, historical fill) | Everywhere | — | 0.25 |

T3 and T4 are never displayed alone as "free".

## B.2 Derivation rule

Over non-suppressed observations in the last `H` hours (12 for buoys, 2 for a busy marina in season):

```
score(obs) = base_trust(source_kind)
           * contributor_reputation      (T2 only, 0.5..1.5 clamped)
           * decay(age)
           * agreement_bonus             (independent sources agreeing: ×1.2, capped at 1.0)

state      = argmax over states of Σ score(obs | obs.state = state)
confidence = winner_mass / total_mass * max_single_score
```

**Asymmetric decay** — half-lives:

| Source | Half-life | Why |
|---|---|---|
| `port_feed` / `sensor` | 60 min, `unknown` past 3 × ttl | A dead feed must not stay green |
| community "occupied" | 8 h, hard expiry 24 h | Boats leave in the morning |
| community "free" | 45 min | A free buoy is taken fast in August |
| community "c'était occupé" | 2 h | Corrective, decays faster than a check-in |
| `ais` | 20 min | Position reports are frequent |

"Free" decays far faster than "occupied": a stale *occupied* costs a look, a stale *free* costs an
hour of daylight and all our credibility.

Display buckets: `≥0.8` confirmé · `0.5–0.8` probable · `0.3–0.5` incertain · `<0.3` → `unknown`.

## B.3 Cold start

1. Pick 3 pilot harbours (1 Atlantique, 1 Méditerranée, 1 Manche) with a motivated capitainerie.
2. Density over breadth for community: enable check-in only where local critical mass is plausible
   (a ZMEL with an active local community — persona P2), not nationally.
3. Ask at the right moment: check-in prompt after 10 min stationary within 30 m of a spot; check-out
   on geofence exit. Never a random notification.
4. **Never fabricate.** No modelled state presented as observed. The French sailing community is
   small and vocal; one caught fabrication ends the project.

## B.4 MBFS — the partner feed spec (draft)

GBFS-shaped, because vendors recognise the pattern and it is proven. Pull (we poll a JSON URL) or
push (they POST deltas or a full snapshot).

```json
{
  "last_updated": "2026-08-06T13:42:00Z", "ttl": 60, "version": "0.1",
  "data": {"harbours": [{
    "harbour_id": "FR-56-CROUESTY",
    "fields": [{
      "field_id": "PANNE-A", "capacity": 48, "visitor_capacity": 12,
      "num_free": 5, "last_reported": "2026-08-06T13:41:30Z",
      "spots": [{"spot_id": "A12", "state": "free", "max_loa_m": 12.0, "max_draft_m": 2.2}]
    }]
  }]}
}
```

- `state ∈ free | occupied | reserved | out_of_service`.
- **`num_free` alone is a valid payload.** Per-berth detail is optional. This removes the two
  objections capitaineries actually raise ("I won't expose my customers", "my system can't").
- Missing heartbeat for 3 × ttl → whole feed `unknown`, UI says *« données du port indisponibles »*.
- Pitch, one line: *we fill your visitor berths and cut the VHF calls; you send one JSON file; you
  switch it off whenever you want.*

## B.5 Community protocol

One tap, no account (anonymous `device_hash`). Offline queue in IndexedDB with original timestamps,
server clamps to `[now-6h, now+5min]`. Implicit check-out on geofence exit at confidence 0.4;
explicit beats implicit. Reputation 1.0 start, +0.05 on independent agreement, −0.2 on
contradiction, floor 0.2 / ceiling 1.5; below 0.4 reports are accepted but weighted ≈ 0
(shadow-weighting — visible bans invite evasion). Rate limit 10/h/device, position plausibility gate
at 500 m, spike detector per device and per zone.

## B.6 Displaying honestly

| State + confidence | UI |
|---|---|
| free ≥ 0.8 | Solid green pin — *« Libre — Port, il y a 2 min »* |
| free 0.5–0.8 | Green outline — *« Probablement libre — Communauté, il y a 40 min »* |
| occupied | Solid grey + source/age |
| unknown / stale | Neutral pin — *« Disponibilité inconnue »* + capitainerie phone button |
| feed down | Neutral pin — *« Données du port indisponibles »* |

**The neutral pin is v1's only state.** Everything ambiguous collapses into it — that discipline is
the whole reason the v1 map and the v2 map can be the same map.
