# 13 — Testing & quality

## What actually deserves tests here

This is a data product. The bugs that hurt are **wrong data shown confidently**, not framework
plumbing. Test priority for **v1**, highest first:

1. **Conflation** ([10](10-ingestion-pipelines.md)) — merges, non-merges, attribute priority.
2. **Source parsing** — S-57 code decoding, OSM tag mapping, WFS paging.
3. **API contract** — filters actually filter; `status` is always `null`; availability params `501`.
4. **Offline journey** — download area → go offline → read → queue a correction → reconnect → flush.
5. **The availability seam** — see below; one test, kept green for the whole life of v1.

Everything else (CRUD, serialisation) gets minimal coverage.

**v2 adds** status derivation ([06 §B.2](06-availability-strategy.md)) as priority 1: decay,
agreement, confidence buckets, and the property tests below. None of it is written in v1 — a pure
function with no callers is not worth testing.

## The seam tests (v1)

Three cheap tests that keep pluggability real rather than aspirational
([06 §A](06-availability-strategy.md)):

```python
def test_seam_carries_status_when_a_provider_is_wired(client_with_fake_provider):
    body = client_with_fake_provider.get("/v1/spots?bbox=-3,47,-2,48").json()
    assert body["features"][0]["properties"]["status"] == {
        "state": "free",
        "confidence": 0.9,
        "as_of": "2026-08-06T13:41:30Z",
        "source_kind": "port_feed",
        "age_seconds": 0,
    }


def test_v1_never_writes_to_availability_tables(db, seeded_referential, exercised_api):
    counts = db.scalar_counts("observation", "spot_status", "field_status", "feed")
    assert counts == {"observation": 0, "spot_status": 0, "field_status": 0, "feed": 0}


def test_availability_flag_has_exactly_one_reference():
    assert grep_count("FEATURE_AVAILABILITY", "api/src") == 1
```

If the first one needs more than swapping the provider to pass, the seam has rotted — fix it in that
PR, not "later".

## Backend

- `pytest`, `pytest-asyncio`, `testcontainers[postgres]` with the **real PostGIS image** — spatial
  SQL must not be mocked; a fake would test nothing.
- **In-memory repository implementations for unit tests**, matching the production interface and
  raising the same domain exceptions. Never mock repository methods.
- Assert **full returned structures** with one comprehensive equality assertion, not a scatter of
  field-by-field checks.
- No tests for trivial instantiation of DTOs, and none for invalid-type arguments — only domain
  validation.

```python
# v2 example — the shape the derivation tests will take
def test_free_report_decays_below_display_threshold(clock):
    spot = InMemorySpotRepo().add(mooring_buoy())
    obs = [community_report(spot, state="free", age=timedelta(minutes=90))]
    assert derive_status(spot, obs, now=clock.now) == SpotStatus(
        state="free",
        confidence=0.19,
        source_kind="community",
        as_of=clock.now - timedelta(minutes=90),
        display_state="unknown",
    )
```

### Golden-file tests for sources

Checked-in real payloads (trimmed) from SHOM WFS, Overpass and one ZMEL dataset, under
`ingest/tests/fixtures/`. Each parser has a golden output. When an upstream schema changes, the
diff is explicit and reviewable — this is the earliest possible warning of a broken referential.

### Property tests *(v2)*

`hypothesis` on the derivation function for the invariants that must never break:

- Confidence ∈ [0, 1] for any observation set.
- Adding an observation that agrees with the current state never lowers confidence.
- A state older than its hard-expire window never wins.
- `free` never wins over a more recent `occupied` from a higher-trust source.

## Frontend

- `vitest` + Testing Library for logic and components; **no snapshot tests of the map**.
- Map layer specs are plain data → unit-test the paint expressions against fixture feature states.
- **Playwright** for the five journeys that matter:
  1. Land on `/`, geolocate (mocked), see spots, filter "libres uniquement".
  2. Open a spot sheet, read depth-at-low-water and status age.
  3. Filter by boat size and depth; the excluded spots disappear from map and list.
  4. **Download an area, go offline (`context.setOffline(true)`), still read it, queue a correction,
     reconnect, verify the flush.**
  5. Harbour page renders prerendered content with JS disabled (SEO guard).
  6. *(v2)* Check in, check out, see the pin change.

## Data-quality tests (run against production nightly, not in CI)

A separate `balise-audit` job asserting:

| Check | Threshold |
|---|---|
| Spots without a source or provenance | 0 |
| Nav aids with an undecodable S-57 code | 0 |
| Spots > 500 m from their field polygon | 0 |
| Duplicate spots within 10 m with the same kind | < 20 nationally |
| Harbours with no contact info | < 10 % |
| Harbours with no phone **and** no VHF channel | 0 — in v1 the phone *is* the availability feature |
| 🔌 *(v2)* `field_status.free_count > capacity` | 0 |
| 🔌 *(v2)* Statuses served as `free` older than their hard expiry | 0 |

Failures open an issue automatically; they do not page anyone at 3 a.m.

### Ground-truth audit

**v1** — the headline quality metric is **position accuracy**: a volunteer GPS-tags 20 moorings in a
bay and we measure the offset against what we display (target: ≥ 90 % within 25 m,
[00](00-vision-and-scope.md)). Run once per season per pilot region. This is what tells us whether
the conflation rules are right, and no unit test substitutes for it.

**v2** — add the availability audit: a volunteer physically counts free buoys in 3 fields at a stated
time; compare with what the app displayed; track **precision of "free"** (target ≥ 85 %, and the M3
exit gate — [14](14-roadmap.md)).

## CI gates (`.github/workflows/ci.yml`)

| Gate | Command | Blocking |
|---|---|---|
| Format | `ruff format --check .` + `prettier --check` | ✅ |
| Lint | `ruff check .`, `eslint` | ✅ |
| Types | `mypy --strict api ingest`, `tsc --noEmit` | ✅ |
| Unit + integration | `pytest`, `vitest` | ✅ |
| E2E | `playwright test` (against a seeded stack) | ✅ on `main`, nightly otherwise |
| Coverage | ≥ 80 % on `conflate.py` and source parsers (v2 adds `availability/status.py`); no global target | ✅ |
| Seam | the three seam tests above | ✅ |
| Bundle budget | `size-limit` per [09](09-frontend-and-map.md) | ✅ |
| Migration check | migration applies to a copy of the staging schema, and is backward-compatible | ✅ |
| Dependency audit | `pip-audit`, `pnpm audit --prod` | ⚠️ warn |

## Definition of done (per feature)

1. Tests at the right level, following the priorities above.
2. `make check` clean.
3. Docs updated when the contract, schema or data source changed — **`docs/` is part of the code**.
4. **v1: it does not touch availability.** No writes to the 🔌 tables, no second reference to
   `FEATURE_AVAILABILITY`, no UI element that assumes a state exists. *(v2: the honesty rules from
   [06 §B.6](06-availability-strategy.md) re-verified — no state without source + age, ambiguity
   collapses to `unknown`.)*
5. If it touches personal data: retention and erasure path updated in [04](04-licensing-and-legal.md).
