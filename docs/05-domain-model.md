# 05 — Domain model & database schema

PostgreSQL 16 + PostGIS 3.4. All geometry in **EPSG:4326**, indexed with GIST; distance work uses
`geography` casts.

> **v1 vs v2.** Everything below is created by the **initial v1 migration**, including the
> availability tables (`observation`, `spot_status`, `field_status`, `feed`, `contributor`), which
> stay **empty in v1**. This is seam S1 ([06 §A](06-availability-strategy.md)): the read path already
> does `LEFT JOIN spot_status`, so the query shape, indexes and cascades are settled and exercised
> from day 1. Six empty tables cost nothing; retrofitting a join into a hot query on a live map does.
> Tables marked 🔌 below have no writer in v1.

## Entities

```
harbour ──1:N── field ──1:N── spot ──1:N── observation
   │                            │
   │                            └──1:1── spot_status   (derived, hot)
   └──1:N── contact / price / service

nav_aid            (separate, read-only, authoritative)
source, feed       (provenance)
report             (community observation subtype)
```

### `harbour`
A port, marina or organised mooring area with an operator. Includes ZMEL managed by a commune.

### `field`
A homogeneous group of spots under one operator: a pontoon (`panne`), a mooring field, a visitor
zone. Carries capacity when individual spots are unknown — a ZMEL of 60 buoys we cannot enumerate is
**one field with `capacity=60`**, not 60 fake spots.

### `spot`
The occupiable unit. `kind ∈ {mooring_buoy, berth, anchorage, pile, quay}`. An `anchorage` spot is a
polygon with a soft capacity, not a discrete object.

### `nav_aid`
Beacons, buoys, lights, landmarks. **No status, ever.** Rendered from vector tiles; the detail sheet
translates S-57 codes into French plain language.

### `observation` 🔌
Append-only. One signal about one spot at one instant, from one source. Never updated, never deleted
(only tombstoned). This is the audit trail behind every green dot. **No writer in v1.**

### `spot_status` 🔌
Derived, one row per spot, recomputed on each observation and by a decay job. Contains `state`,
`confidence`, `as_of`, `source_kind`, `observation_id`. **Empty in v1** — the read path joins it and
gets `NULL`, which serialises to `"status": null` ([06 §A/S3](06-availability-strategy.md)).

## Schema (DDL)

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TYPE spot_kind   AS ENUM ('mooring_buoy','berth','anchorage','pile','quay');
CREATE TYPE spot_state  AS ENUM ('free','occupied','reserved','out_of_service','unknown');
CREATE TYPE source_kind AS ENUM ('port_feed','sensor','community','ais','manual','import');

-- provenance -------------------------------------------------------------
CREATE TABLE source (
  id            text PRIMARY KEY,              -- 'shom.balisage', 'osm', 'zmel.56', 'feed.port-crouesty'
  kind          source_kind NOT NULL,
  licence       text NOT NULL,                 -- 'etalab-2.0', 'odbl-1.0', 'proprietary'
  attribution   text NOT NULL,
  url           text,
  last_sync_at  timestamptz
);

-- referential ------------------------------------------------------------
CREATE TABLE harbour (
  id            bigserial PRIMARY KEY,
  slug          text UNIQUE NOT NULL,          -- 'port-du-crouesty' → SEO route
  name          text NOT NULL,
  insee_code    text,                          -- commune
  geom          geometry(Point,4326) NOT NULL,
  area          geometry(MultiPolygon,4326),
  vhf_channel   smallint,
  phone         text,
  email         text,
  website       text,
  opening_hours text,                          -- OSM syntax
  services      text[] NOT NULL DEFAULT '{}',  -- water, fuel, wifi, careening, waste
  source_id     text NOT NULL REFERENCES source(id),
  external_ids  jsonb NOT NULL DEFAULT '{}',   -- {"osm":"way/123","shom":"FR0000..."}
  attrs_provenance jsonb NOT NULL DEFAULT '{}',
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON harbour USING gist (geom);
CREATE INDEX ON harbour USING gin (name gin_trgm_ops);

CREATE TABLE field (
  id            bigserial PRIMARY KEY,
  harbour_id    bigint REFERENCES harbour(id) ON DELETE CASCADE,
  name          text,
  kind          spot_kind NOT NULL,
  area          geometry(MultiPolygon,4326),
  capacity      integer,                       -- total spots, incl. non-enumerated
  visitor_capacity integer,
  operator      text,
  price_per_night_cents integer,
  price_note    text,
  source_id     text NOT NULL REFERENCES source(id),
  external_ids  jsonb NOT NULL DEFAULT '{}',
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON field USING gist (area);

CREATE TABLE spot (
  id            bigserial PRIMARY KEY,
  field_id      bigint REFERENCES field(id) ON DELETE SET NULL,
  harbour_id    bigint REFERENCES harbour(id) ON DELETE SET NULL,
  kind          spot_kind NOT NULL,
  code          text,                          -- 'A12', buoy number painted on it
  geom          geometry(Point,4326) NOT NULL,
  area          geometry(Polygon,4326),        -- anchorage only
  depth_m       numeric(4,1),                  -- charted depth, chart datum
  max_loa_m     numeric(4,1),
  max_beam_m    numeric(4,1),
  max_draft_m   numeric(4,1),
  holding       text,                          -- sand, mud, weed, rock
  exposure      text[] NOT NULL DEFAULT '{}',  -- exposed sectors: {'N','NE'}
  visitor       boolean NOT NULL DEFAULT false,
  bookable      boolean NOT NULL DEFAULT false,
  source_id     text NOT NULL REFERENCES source(id),
  external_ids  jsonb NOT NULL DEFAULT '{}',
  attrs_provenance jsonb NOT NULL DEFAULT '{}',
  active        boolean NOT NULL DEFAULT true,
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON spot USING gist (geom);
CREATE INDEX ON spot (field_id);
CREATE INDEX ON spot (kind) WHERE active;

CREATE TABLE nav_aid (
  id            bigserial PRIMARY KEY,
  inspire_id    text UNIQUE,                   -- SHOM 'FR000001090900001'
  s57_class     text NOT NULL,                 -- 'boylat','bcncar','lndmrk'…
  geom          geometry(Point,4326) NOT NULL,
  name          text,                          -- objnam / nobjnm
  colour        text,                          -- S-57 code list, raw
  colour_pattern text,
  shape         text,                          -- boyshp
  topmark       text,
  category      text,                          -- catlam, catcam…
  light         jsonb,                         -- {"character":"Fl","period":4,"colour":"R","range":7}
  height_m      numeric(5,1),
  source_id     text NOT NULL REFERENCES source(id),
  raw           jsonb NOT NULL,                -- full original properties, never lossy
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON nav_aid USING gist (geom);

-- availability -----------------------------------------------------------
-- 🔌 created in v1, written to only in v2 (docs/06 §A/S1)
CREATE TABLE feed (
  id            text PRIMARY KEY,              -- 'feed.port-crouesty'
  harbour_id    bigint NOT NULL REFERENCES harbour(id),
  kind          source_kind NOT NULL,
  contact_email text NOT NULL,
  token_hash    text NOT NULL,
  pull_url      text,                          -- if we poll instead of them pushing
  poll_seconds  integer,
  trust         numeric(3,2) NOT NULL DEFAULT 0.95,
  active        boolean NOT NULL DEFAULT true,
  last_seen_at  timestamptz
);

CREATE TABLE observation (
  id            bigserial PRIMARY KEY,
  spot_id       bigint REFERENCES spot(id) ON DELETE CASCADE,
  field_id      bigint REFERENCES field(id) ON DELETE CASCADE,  -- aggregate obs (n free of N)
  state         spot_state NOT NULL,
  free_count    integer,                       -- field-level only
  source_kind   source_kind NOT NULL,
  source_ref    text,                          -- feed id, contributor hash, MMSI
  observed_at   timestamptz NOT NULL,
  received_at   timestamptz NOT NULL DEFAULT now(),
  confidence    numeric(3,2) NOT NULL,         -- 0..1 at emission
  payload       jsonb NOT NULL DEFAULT '{}',
  suppressed    boolean NOT NULL DEFAULT false,
  CHECK (spot_id IS NOT NULL OR field_id IS NOT NULL)
);
CREATE INDEX ON observation (spot_id, observed_at DESC);
CREATE INDEX ON observation (field_id, observed_at DESC);
CREATE INDEX ON observation (received_at DESC);
-- partition by month on observed_at once > 50M rows

CREATE TABLE spot_status (
  spot_id       bigint PRIMARY KEY REFERENCES spot(id) ON DELETE CASCADE,
  state         spot_state NOT NULL,
  confidence    numeric(3,2) NOT NULL,
  as_of         timestamptz NOT NULL,
  source_kind   source_kind NOT NULL,
  observation_id bigint REFERENCES observation(id),
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON spot_status (state, confidence DESC);

CREATE TABLE field_status (
  field_id      bigint PRIMARY KEY REFERENCES field(id) ON DELETE CASCADE,
  free_count    integer,
  capacity      integer,
  confidence    numeric(3,2) NOT NULL,
  as_of         timestamptz NOT NULL,
  source_kind   source_kind NOT NULL
);

-- community --------------------------------------------------------------
-- 🔌 contributor exists in v1 to attribute *data corrections*; comment/photos are v2
CREATE TABLE contributor (
  id            bigserial PRIMARY KEY,
  device_hash   text UNIQUE NOT NULL,          -- salted, rotated every 6 months
  email         text UNIQUE,
  reputation    numeric(4,2) NOT NULL DEFAULT 1.0,
  banned        boolean NOT NULL DEFAULT false,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE comment (
  id            bigserial PRIMARY KEY,
  spot_id       bigint REFERENCES spot(id) ON DELETE CASCADE,
  harbour_id    bigint REFERENCES harbour(id) ON DELETE CASCADE,
  contributor_id bigint NOT NULL REFERENCES contributor(id),
  body          text NOT NULL,
  rating        smallint CHECK (rating BETWEEN 1 AND 5),
  photo_keys    text[] NOT NULL DEFAULT '{}',
  moderated     boolean NOT NULL DEFAULT false,
  created_at    timestamptz NOT NULL DEFAULT now()
);

-- environment cache ------------------------------------------------------
CREATE TABLE tide_prediction (
  harbour_id    bigint NOT NULL REFERENCES harbour(id),
  at            timestamptz NOT NULL,
  height_m      numeric(4,2) NOT NULL,
  kind          text,                          -- 'HW','LW', NULL for curve points
  coefficient   smallint,
  PRIMARY KEY (harbour_id, at)
);

CREATE TABLE weather_forecast (
  harbour_id    bigint NOT NULL REFERENCES harbour(id),
  at            timestamptz NOT NULL,
  wind_kt       numeric(4,1),
  gust_kt       numeric(4,1),
  wind_dir_deg  smallint,
  wave_m        numeric(4,2),
  fetched_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (harbour_id, at)
);
```

## ID strategy

- **Internal**: `bigserial`, never exposed as meaningful. Public API exposes them as opaque strings.
- **External**: kept in `external_ids jsonb` — `{"shom":"FR0000…","osm":"node/1234","zmel56":"…"}`.
  Idempotent ingestion keys on these, never on geometry.
- **Slug**: `harbour.slug` is the SEO-stable public identifier (`/port/port-du-crouesty`). Renaming a
  harbour keeps the old slug as a redirect (`slug_alias` table when needed).

## Attribute provenance

`attrs_provenance` maps attribute → source id: `{"depth_m":"shom.balisage","max_loa_m":"osm"}`.
Required for [04 §2](04-licensing-and-legal.md) (ODbL separation) and for debugging conflation.

## Invariants (enforced in tests)

1. A `nav_aid` never has a status and never appears in the `/spots` API.
2. Every `spot` has exactly one `source_id` and a non-empty `attrs_provenance`.
3. `spot_status.as_of` ≤ `now()`, and `state='free'` with `confidence < 0.4` is never served as free.
4. `observation` rows are immutable: only `suppressed` may flip.
5. `field.capacity >= field_status.free_count` always.
6. **v1 only:** `spot_status`, `field_status`, `observation` and `feed` are empty. A test asserts
   `SELECT count(*) = 0` on each after a full ingest + a full e2e run — if something starts writing
   to them, availability has leaked into v1 and the review missed it.
