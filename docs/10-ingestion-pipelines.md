# 10 — Ingestion pipelines

Four stages, one command each, all idempotent, all re-runnable from raw snapshots.

```
fetch → raw/{source}/{date}/*.json    (immutable snapshot, gzipped, kept 90 days)
normalise → staging tables shom_*, osm_*, zmel_*
conflate → resolve duplicates across sources, decide attribute winners
load → referential tables (harbour, field, spot, nav_aid) in one transaction
```

Snapshots are kept because **conflation rules will change** and we must re-derive without hammering
the sources.

## Schedule

| Source | Frequency | Job |
|---|---|---|
| SHOM balisage (16 layers) | weekly, Monday 03:00 | `balise-ingest shom balisage` |
| SHOM ports / réglementation | monthly | `balise-ingest shom ports` |
| OSM France extract | daily 04:00 (Geofabrik `.osm.pbf`) | `balise-ingest osm full` |
| OSM deltas (Overpass) | hourly, coastal bbox, changed nodes only | `balise-ingest osm delta` |
| ZMEL / data.gouv datasets | quarterly, manual review | `balise-ingest datagouv zmel --dept 56` |
| Tides | daily, 7 days ahead, per reference port | `balise-ingest tides` |
| Weather | hourly, per harbour | `balise-ingest weather` |

## SHOM — WFS paging

```python
BASE = "https://services.data.shom.fr/INSPIRE/wfs"
PAGE = 1000


async def fetch_layer(client: httpx.AsyncClient, type_name: str) -> list[dict]:
    features: list[dict] = []
    start = 0
    while True:
        r = await client.get(
            BASE,
            params={
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "typeNames": type_name,
                "outputFormat": "application/json",
                "srsName": "EPSG:4326",
                "count": PAGE,
                "startIndex": start,
            },
            timeout=120,
        )
        r.raise_for_status()
        page = r.json()
        features.extend(page["features"])
        if page["numberReturned"] < PAGE:
            return features
        start += PAGE
```

Notes:
- `numberMatched` is returned on every page — assert the final count matches, fail the job otherwise.
- Layers are small (`morfac` = 1 394, `achare_point` = 790, all layers together well under 10⁵).
- **Never** silently drop unknown attributes: the whole `properties` object goes into `nav_aid.raw`.
- S-57 code lists (`catmor`, `boyshp`, `colour`, `catlam`, `catcam`, light `litchr`) are decoded via
  a checked-in mapping table `ingest/s57_codes.py`, with a test asserting every code seen in
  production data has a French label. An unknown code fails the job loudly rather than rendering an
  unlabelled mark.

## OSM

Bulk path (daily): download `europe/france-latest.osm.pbf` from Geofabrik, filter with `osmium`:

```bash
osmium tags-filter france-latest.osm.pbf \
  n/seamark:type w/leisure=marina n/leisure=marina r/leisure=marina \
  w/man_made=pier n/seamark:type=mooring \
  -o seamarks.osm.pbf
osmium export seamarks.osm.pbf -f geojsonseq -o seamarks.geojsonseq
```

Delta path (hourly): Overpass with `[bbox]` per coastal region and `newer:` filter; used only to keep
the map fresh between bulk runs. Respect Overpass etiquette (≤ 1 query/min, `User-Agent` with a
contact address) or self-host an instance once volume justifies it.

Mapping table: [03 §B](03-data-sources.md).

## ZMEL / data.gouv

Heterogeneous by département — a per-dataset adapter under `ingest/adapters/zmel_{dept}.py`
implementing:

```python
class ZmelAdapter(Protocol):
    dept: str
    url: str

    def to_fields(self, raw: dict) -> list[FieldRecord]: ...
```

Expected reality: some give polygons with a `nb_bouees` attribute (→ one `field` with `capacity`),
some give points per buoy (→ `spot` rows), some give only a site name (→ `field` with unknown
capacity). All three are acceptable; the model handles them ([05](05-domain-model.md)).

## Conflation

The core problem: the same mooring appears in OSM and possibly SHOM/ZMEL, with slightly different
positions.

**Algorithm**

1. Bucket candidates by 100 m grid cell + `kind`.
2. Match if `ST_DWithin(a.geom, b.geom, 25 m)` **and** kinds are compatible **and** (codes match or
   both codes are null). 25 m ≈ typical GPS + charting error for a buoy; tuned per kind
   (berths: 8 m, anchorages: polygon overlap ≥ 50 %).
3. On match, merge with a **fixed source priority per attribute**:

| Attribute | Priority |
|---|---|
| position of a nav aid | SHOM > OSM |
| position of a mooring buoy | ZMEL (surveyed) > OSM > SHOM |
| capacity, prices, contacts | operator/partner > ZMEL > OSM |
| name | operator > OSM > SHOM |
| depth | SHOM > OSM |

4. Record every merge in `conflation_log` (both source ids, distance, rule fired) — this is the only
   way to debug "why did my buoy move".
5. **Never delete on absence.** A spot missing from one run is marked `active=false` after **three**
   consecutive absences from an authoritative source, never on the first.

**Manual overrides** live in a checked-in YAML (`ingest/overrides.yml`) applied last: pinned
positions, forced merges/splits, blacklisted objects. Data corrections must be reviewable in git.

## Loading

- One transaction per source per run. `INSERT … ON CONFLICT (external_id) DO UPDATE`.
- Bump `ref_version` (a row in a `meta` table) at the end → invalidates tile ETags
  ([07](07-architecture.md)).
- Emit metrics: features fetched, inserted, updated, deactivated, conflated, rejected. Alert if
  any count moves > 20 % versus the previous run — that pattern catches an upstream schema change
  before users see an empty map.

## Failure policy

| Failure | Behaviour |
|---|---|
| Source unreachable | Retry ×3 with backoff, then keep previous data, alert. **Never** wipe. |
| Schema change (unknown field/code) | Fail the job, keep previous data, alert with the offending payload |
| Count anomaly > 20 % | Load into staging, block promotion, require manual `--force` |
| Partial page failure | Fail the whole layer; snapshots are all-or-nothing |

## Local run

```bash
uv run balise-ingest shom balisage --dry-run          # fetch + normalise, no load
uv run balise-ingest shom balisage --bbox -3.2,47.4,-2.6,47.8   # dev subset (Morbihan)
uv run balise-ingest osm full --from-snapshot raw/osm/2026-08-05
uv run balise-ingest conflate --kind mooring_buoy --explain spot_18421
```

`--explain` prints the conflation trace for one object. Use it before touching the rules.
