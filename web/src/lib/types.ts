/**
 * Hand-written mirror of the API contract (docs/08) for the few shapes the UI needs.
 * `pnpm gen:api` regenerates the full set from the OpenAPI schema into `api-types.ts`;
 * these narrow aliases keep the components readable and are asserted by tests.
 */

export type SpotKind = 'mooring_buoy' | 'berth' | 'anchorage' | 'pile' | 'quay'
export type SpotState = 'free' | 'occupied' | 'reserved' | 'out_of_service' | 'unknown'
export type SourceKind = 'port_feed' | 'sensor' | 'community' | 'ais' | 'manual' | 'import'
export type ConfidenceBucket = 'confirmed' | 'probable' | 'uncertain' | 'unknown'

export interface Status {
  state: SpotState
  confidence: number
  bucket: ConfidenceBucket
  /** Absent when the state is `unknown`: nothing to date, nothing to attribute. */
  as_of: string | null
  source_kind: SourceKind | null
  age_seconds: number | null
}

export interface SpotProperties {
  kind: SpotKind
  code: string | null
  harbour_id: string | null
  harbour_name: string | null
  field_id: string | null
  visitor: boolean
  depth_m: number | null
  max_loa_m: number | null
  max_draft_m: number | null
  max_beam_m: number | null
  holding: string | null
  exposure: string[]
  price_per_night_cents: number | null
  /** `null` in v1, and in v2 for any spot nobody has reported. Treat null as unknown (docs/08). */
  status: Status | null
}

export interface Feature {
  type: 'Feature'
  id: string
  geometry: { type: 'Point'; coordinates: [number, number] }
  properties: SpotProperties
}

export interface FeatureCollection {
  type: 'FeatureCollection'
  features: Feature[]
  attribution: string[]
  next_cursor: string | null
  disclaimer: string
}

export interface TideExtreme {
  at: string
  height_m: number
  kind: string
  coefficient: number | null
}

export interface TideSummary {
  harbour_id: string
  next_high_water: TideExtreme | null
  next_low_water: TideExtreme | null
  depth_at_next_low_water_m: number | null
  is_estimate: boolean
  note: string
  attribution: string[]
}

export interface WeatherPoint {
  at: string
  wind_kt: number | null
  gust_kt: number | null
  wind_dir_deg: number | null
  wave_m: number | null
}

export interface WeatherSummary {
  harbour_id: string
  points: WeatherPoint[]
  is_estimate: boolean
  attribution: string[]
}

export interface FieldStatus {
  free: number | null
  capacity: number | null
  confidence: number
  as_of: string | null
  source_kind: SourceKind | null
}

export interface FieldSummary {
  id: string
  name: string | null
  kind: SpotKind
  capacity: number | null
  visitor_capacity: number | null
  operator: string | null
  price_per_night_cents: number | null
  price_note: string | null
  status: FieldStatus | null
}

export interface HarbourSummary {
  id: string
  slug: string
  name: string
  vhf_channel: number | null
  phone: string | null
  website: string | null
  opening_hours: string | null
  services: string[]
}

export interface ObservationTrace {
  source_kind: SourceKind
  state: SpotState
  age_seconds: number
  confidence: number
}

export interface SpotDetail {
  id: string
  kind: SpotKind
  code: string | null
  position: [number, number]
  properties: SpotProperties
  field: FieldSummary | null
  harbour: HarbourSummary | null
  /** 🔌 empty in v1; v2 adds the last 5 observations (source kind and age only). */
  observations: ObservationTrace[]
  tide: TideSummary | null
  weather: WeatherSummary | null
  warnings: string[]
  attribution: string[]
  disclaimer: string
}

export interface HarbourListItem {
  id: string
  slug: string
  name: string
  position: [number, number]
  insee_code: string | null
  distance_nm: number | null
  spot_count: number
}

export interface HarbourList {
  harbours: HarbourListItem[]
  attribution: string[]
}

export interface HarbourDetail extends HarbourSummary {
  position: [number, number]
  insee_code: string | null
  email: string | null
  fields: FieldSummary[]
  spot_count: number
  attribution: string[]
  disclaimer: string
}

export interface NavAidDetail {
  id: string
  s57_class: string
  label: string
  name: string | null
  colour: string | null
  colour_pattern: string | null
  shape: string | null
  topmark: string | null
  category: string | null
  height_m: number | null
  light: {
    text: string
    character: string | null
    period_s: number | null
    colour: string | null
    range_nm: number | null
  } | null
  position: [number, number]
  explainer: string
  source: string
  disclaimer: string
}

export interface StatusMap {
  as_of: string
  spots: Record<string, [SpotState, number, string, SourceKind]>
  fields: Record<string, { free: number | null; capacity: number | null; confidence: number }>
}

export interface ReportOut {
  observation_id: string
  spot_id: string
  status: Status
  clamped: boolean
  remote: boolean
  duplicate: boolean
}

export type TargetType = 'spot' | 'harbour' | 'navaid'
export type CorrectionKind =
  'wrong_position' | 'removed' | 'wrong_price' | 'wrong_contact' | 'wrong_name' | 'other'

/** v1's queued contribution: a correction to the referential, never a state (docs/08). */
export interface QueuedCorrection {
  id: string
  target: { type: TargetType; id: string }
  kind: CorrectionKind
  note: string
  created_at: string
  position?: [number, number]
}

export interface IssueOut {
  id: string
  kind: CorrectionKind
  created_at: string
  note: string
}

/** 🔌 v2 — the availability report, kept typed so the v2 client is a diff, not a rewrite. */
export interface QueuedReport {
  id: string
  spot_id: string
  state: 'free' | 'occupied' | 'out_of_service'
  report_kind: 'check_in' | 'check_out' | 'correction'
  observed_at: string
  position?: [number, number]
  note?: string
}
