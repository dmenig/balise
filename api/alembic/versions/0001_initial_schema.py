"""Initial schema — docs/05 domain model, verbatim DDL plus provenance staging.

Revision ID: 0001
Revises:
"""

from __future__ import annotations

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

DDL = """
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TYPE spot_kind   AS ENUM ('mooring_buoy','berth','anchorage','pile','quay');
CREATE TYPE spot_state  AS ENUM ('free','occupied','reserved','out_of_service','unknown');
CREATE TYPE source_kind AS ENUM ('port_feed','sensor','community','ais','manual','import');

CREATE TABLE meta (
  key        text PRIMARY KEY,
  value      text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO meta (key, value) VALUES ('ref_version', '0');

CREATE TABLE source (
  id            text PRIMARY KEY,
  kind          source_kind NOT NULL,
  licence       text NOT NULL,
  attribution   text NOT NULL,
  url           text,
  last_sync_at  timestamptz
);

CREATE TABLE harbour (
  id            bigserial PRIMARY KEY,
  slug          text UNIQUE NOT NULL,
  name          text NOT NULL,
  insee_code    text,
  geom          geometry(Point,4326) NOT NULL,
  area          geometry(MultiPolygon,4326),
  vhf_channel   smallint,
  phone         text,
  email         text,
  website       text,
  opening_hours text,
  services      text[] NOT NULL DEFAULT '{}',
  source_id     text NOT NULL REFERENCES source(id),
  external_ids  jsonb NOT NULL DEFAULT '{}',
  attrs_provenance jsonb NOT NULL DEFAULT '{}',
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_harbour_geom ON harbour USING gist (geom);
CREATE INDEX ix_harbour_name_trgm ON harbour USING gin (name gin_trgm_ops);

CREATE TABLE field (
  id            bigserial PRIMARY KEY,
  harbour_id    bigint REFERENCES harbour(id) ON DELETE CASCADE,
  name          text,
  kind          spot_kind NOT NULL,
  area          geometry(MultiPolygon,4326),
  capacity      integer,
  visitor_capacity integer,
  operator      text,
  price_per_night_cents integer,
  price_note    text,
  source_id     text NOT NULL REFERENCES source(id),
  external_ids  jsonb NOT NULL DEFAULT '{}',
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_field_area ON field USING gist (area);
CREATE INDEX ix_field_harbour_id ON field (harbour_id);

CREATE TABLE spot (
  id            bigserial PRIMARY KEY,
  field_id      bigint REFERENCES field(id) ON DELETE SET NULL,
  harbour_id    bigint REFERENCES harbour(id) ON DELETE SET NULL,
  kind          spot_kind NOT NULL,
  code          text,
  geom          geometry(Point,4326) NOT NULL,
  area          geometry(Polygon,4326),
  depth_m       numeric(4,1),
  max_loa_m     numeric(4,1),
  max_beam_m    numeric(4,1),
  max_draft_m   numeric(4,1),
  holding       text,
  exposure      text[] NOT NULL DEFAULT '{}',
  visitor       boolean NOT NULL DEFAULT false,
  bookable      boolean NOT NULL DEFAULT false,
  source_id     text NOT NULL REFERENCES source(id),
  external_ids  jsonb NOT NULL DEFAULT '{}',
  attrs_provenance jsonb NOT NULL DEFAULT '{}',
  active        boolean NOT NULL DEFAULT true,
  missing_runs  integer NOT NULL DEFAULT 0,
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_spot_geom ON spot USING gist (geom);
CREATE INDEX ix_spot_field_id ON spot (field_id);
CREATE INDEX ix_spot_kind_active ON spot (kind) WHERE active;
CREATE INDEX ix_spot_external_ids ON spot USING gin (external_ids jsonb_path_ops);

CREATE TABLE nav_aid (
  id            bigserial PRIMARY KEY,
  inspire_id    text UNIQUE,
  s57_class     varchar(16) NOT NULL,
  geom          geometry(Point,4326) NOT NULL,
  name          text,
  colour        text,
  colour_pattern text,
  shape         text,
  topmark       text,
  category      text,
  light         jsonb,
  height_m      numeric(5,1),
  source_id     text NOT NULL REFERENCES source(id),
  raw           jsonb NOT NULL,
  active        boolean NOT NULL DEFAULT true,
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_nav_aid_geom ON nav_aid USING gist (geom);
CREATE INDEX ix_nav_aid_class ON nav_aid (s57_class);

CREATE TABLE conflation_log (
  id                bigserial PRIMARY KEY,
  run_id            text NOT NULL,
  target_table      text NOT NULL,
  target_id         bigint,
  left_source_id    text NOT NULL,
  left_external_id  text NOT NULL,
  right_source_id   text,
  right_external_id text,
  distance_m        numeric(8,2),
  rule              text NOT NULL,
  detail            jsonb NOT NULL DEFAULT '{}',
  created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_conflation_log_run_id ON conflation_log (run_id);
CREATE INDEX ix_conflation_log_target_id ON conflation_log (target_id);

CREATE TABLE contributor (
  id            bigserial PRIMARY KEY,
  device_hash   text UNIQUE NOT NULL,
  email         text UNIQUE,
  reputation    numeric(4,2) NOT NULL DEFAULT 1.0,
  banned        boolean NOT NULL DEFAULT false,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE feed (
  id            text PRIMARY KEY,
  harbour_id    bigint NOT NULL REFERENCES harbour(id),
  kind          source_kind NOT NULL,
  contact_email text NOT NULL,
  token_hash    text NOT NULL,
  pull_url      text,
  poll_seconds  integer,
  ttl_seconds   integer NOT NULL DEFAULT 60,
  trust         numeric(3,2) NOT NULL DEFAULT 0.95,
  active        boolean NOT NULL DEFAULT true,
  last_seen_at  timestamptz,
  accepted_24h  integer NOT NULL DEFAULT 0,
  rejected_24h  integer NOT NULL DEFAULT 0
);

CREATE TABLE observation (
  id            bigserial PRIMARY KEY,
  spot_id       bigint REFERENCES spot(id) ON DELETE CASCADE,
  field_id      bigint REFERENCES field(id) ON DELETE CASCADE,
  state         spot_state NOT NULL,
  free_count    integer,
  source_kind   source_kind NOT NULL,
  source_ref    text,
  contributor_id bigint REFERENCES contributor(id) ON DELETE SET NULL,
  observed_at   timestamptz NOT NULL,
  received_at   timestamptz NOT NULL DEFAULT now(),
  confidence    numeric(3,2) NOT NULL,
  payload       jsonb NOT NULL DEFAULT '{}',
  suppressed    boolean NOT NULL DEFAULT false,
  idempotency_key text UNIQUE,
  CONSTRAINT ck_observation_target CHECK (spot_id IS NOT NULL OR field_id IS NOT NULL)
);
CREATE INDEX ix_observation_spot ON observation (spot_id, observed_at DESC);
CREATE INDEX ix_observation_field ON observation (field_id, observed_at DESC);
CREATE INDEX ix_observation_received ON observation (received_at DESC);
CREATE INDEX ix_observation_contributor ON observation (contributor_id);

CREATE TABLE spot_status (
  spot_id       bigint PRIMARY KEY REFERENCES spot(id) ON DELETE CASCADE,
  state         spot_state NOT NULL,
  confidence    numeric(3,2) NOT NULL,
  as_of         timestamptz NOT NULL,
  source_kind   source_kind NOT NULL,
  observation_id bigint REFERENCES observation(id) ON DELETE SET NULL,
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_spot_status_state ON spot_status (state, confidence DESC);
CREATE INDEX ix_spot_status_updated ON spot_status (updated_at DESC);

CREATE TABLE field_status (
  field_id      bigint PRIMARY KEY REFERENCES field(id) ON DELETE CASCADE,
  free_count    integer,
  capacity      integer,
  confidence    numeric(3,2) NOT NULL,
  as_of         timestamptz NOT NULL,
  source_kind   source_kind NOT NULL,
  updated_at    timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_field_status_capacity
    CHECK (capacity IS NULL OR free_count IS NULL OR free_count <= capacity)
);
CREATE INDEX ix_field_status_updated ON field_status (updated_at DESC);

CREATE TABLE comment (
  id            bigserial PRIMARY KEY,
  spot_id       bigint REFERENCES spot(id) ON DELETE CASCADE,
  harbour_id    bigint REFERENCES harbour(id) ON DELETE CASCADE,
  contributor_id bigint NOT NULL REFERENCES contributor(id),
  body          text NOT NULL,
  rating        smallint,
  photo_keys    text[] NOT NULL DEFAULT '{}',
  moderated     boolean NOT NULL DEFAULT false,
  created_at    timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_comment_rating CHECK (rating IS NULL OR rating BETWEEN 1 AND 5)
);

CREATE TABLE issue (
  id            bigserial PRIMARY KEY,
  spot_id       bigint REFERENCES spot(id) ON DELETE CASCADE,
  harbour_id    bigint REFERENCES harbour(id) ON DELETE CASCADE,
  nav_aid_id    bigint REFERENCES nav_aid(id) ON DELETE CASCADE,
  contributor_id bigint REFERENCES contributor(id),
  category      text NOT NULL,
  body          text NOT NULL,
  payload       jsonb NOT NULL DEFAULT '{}',
  resolved      boolean NOT NULL DEFAULT false,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE tide_prediction (
  harbour_id    bigint NOT NULL REFERENCES harbour(id) ON DELETE CASCADE,
  at            timestamptz NOT NULL,
  height_m      numeric(4,2) NOT NULL,
  kind          text,
  coefficient   smallint,
  fetched_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (harbour_id, at)
);

CREATE TABLE weather_forecast (
  harbour_id    bigint NOT NULL REFERENCES harbour(id) ON DELETE CASCADE,
  at            timestamptz NOT NULL,
  wind_kt       numeric(4,1),
  gust_kt       numeric(4,1),
  wind_dir_deg  smallint,
  wave_m        numeric(4,2),
  fetched_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (harbour_id, at)
);
"""

STAGING_DDL = """
CREATE TABLE shom_feature (
  id            bigserial PRIMARY KEY,
  external_id   text NOT NULL,
  layer         text NOT NULL,
  geom          geometry(Geometry,4326),
  properties    jsonb NOT NULL,
  snapshot_date text NOT NULL,
  fetched_at    timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_shom_feature UNIQUE (layer, external_id)
);
CREATE INDEX ix_shom_feature_geom ON shom_feature USING gist (geom);

CREATE TABLE osm_feature (
  id            bigserial PRIMARY KEY,
  external_id   text NOT NULL,
  layer         text NOT NULL,
  geom          geometry(Geometry,4326),
  properties    jsonb NOT NULL,
  snapshot_date text NOT NULL,
  fetched_at    timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_osm_feature UNIQUE (layer, external_id)
);
CREATE INDEX ix_osm_feature_geom ON osm_feature USING gist (geom);

CREATE TABLE zmel_feature (
  id            bigserial PRIMARY KEY,
  external_id   text NOT NULL,
  layer         text NOT NULL,
  geom          geometry(Geometry,4326),
  properties    jsonb NOT NULL,
  snapshot_date text NOT NULL,
  fetched_at    timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_zmel_feature UNIQUE (layer, external_id)
);
CREATE INDEX ix_zmel_feature_geom ON zmel_feature USING gist (geom);
"""

DROP = """
DROP TABLE IF EXISTS zmel_feature, osm_feature, shom_feature, weather_forecast, tide_prediction,
  issue, comment, field_status, spot_status, observation, feed, contributor, conflation_log,
  nav_aid, spot, field, harbour, source, meta CASCADE;
DROP TYPE IF EXISTS source_kind;
DROP TYPE IF EXISTS spot_state;
DROP TYPE IF EXISTS spot_kind;
"""


def upgrade() -> None:
    op.execute(DDL)
    op.execute(STAGING_DDL)


def downgrade() -> None:
    op.execute(DROP)
