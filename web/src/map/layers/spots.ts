/**
 * Layer definitions as data, not JSX (docs/11), so the paint expressions can be unit-tested
 * against fixture feature states.
 *
 * **S5 — the UI seam (docs/06 §A/S5, docs/09).** The expressions below are written in their final
 * v2 form: they read `feature-state` and fall back to the neutral style when it is unset. In v1
 * nothing calls `setFeatureState`, so every spot renders neutral and only the fallback branch is
 * taken. Enabling availability = starting to call it. None of this is dead code — "nobody has
 * reported this spot" stays the common case in v2.
 *
 * In v1 spots are differentiated by **kind**, the only meaningful axis when there is no state, with
 * a shape that cannot be mistaken for a chart symbol.
 */
import type {
  CircleLayerSpecification,
  ExpressionSpecification,
  FillLayerSpecification,
  FilterSpecification,
  SymbolLayerSpecification,
} from 'maplibre-gl'

export const COLOURS = {
  free: '#1F9D55',
  freeSoft: '#7BC08F',
  occupied: '#6B7280',
  /** The neutral pin: v1's only state. It must read as "the map", never as a loading state. */
  unknown: '#3d7f9e',
} as const

/** Kind is what v1 has to say about a spot, so kind is what the pin says. */
export const KIND_COLOURS = {
  mooring_buoy: '#3d7f9e',
  berth: '#1d4d64',
  anchorage: '#8fbcd4',
  pile: '#5b7f8f',
  quay: '#26586e',
} as const

export const spotKindColour: ExpressionSpecification = [
  'match',
  ['get', 'kind'],
  'mooring_buoy',
  KIND_COLOURS.mooring_buoy,
  'berth',
  KIND_COLOURS.berth,
  'anchorage',
  KIND_COLOURS.anchorage,
  'pile',
  KIND_COLOURS.pile,
  'quay',
  KIND_COLOURS.quay,
  COLOURS.unknown,
]

/**
 * Final v2 colour ramp. `feature-state` is unset in v1, so this always evaluates to the neutral
 * branch — which is the kind colour, not a fourth grey nobody chose.
 */
export const spotColour: ExpressionSpecification = [
  'case',
  ['==', ['feature-state', 'state'], 'free'],
  [
    'case',
    ['>=', ['coalesce', ['feature-state', 'confidence'], 0], 0.8],
    COLOURS.free,
    COLOURS.freeSoft,
  ],
  ['==', ['feature-state', 'state'], 'occupied'],
  COLOURS.occupied,
  spotKindColour,
]

export const spotsLayer: CircleLayerSpecification = {
  id: 'spots',
  type: 'circle',
  source: 'spots',
  'source-layer': 'spots',
  paint: {
    'circle-radius': ['interpolate', ['linear'], ['zoom'], 11, 4, 14, 9, 17, 14],
    'circle-color': spotColour,
    'circle-stroke-width': 2,
    'circle-stroke-color': '#ffffff',
    'circle-opacity': 0.95,
  },
}

/** The kind glyph: a buoy, a berth and an anchorage must be distinguishable without colour. */
export const spotKindGlyph: ExpressionSpecification = [
  'match',
  ['get', 'kind'],
  'mooring_buoy',
  '○',
  'berth',
  '▭',
  'anchorage',
  '⚓',
  'pile',
  '|',
  'quay',
  '▬',
  '·',
]

export const spotGlyphLayer: SymbolLayerSpecification = {
  id: 'spots-glyph',
  type: 'symbol',
  source: 'spots',
  'source-layer': 'spots',
  minzoom: 13,
  layout: {
    // `kind` comes from the tile, so this stays a legal layout property — unlike `feature-state`,
    // which MapLibre refuses in layout and which is exactly why status lives in paint only.
    'text-field': spotKindGlyph,
    'text-size': 10,
    'text-allow-overlap': true,
  },
  paint: { 'text-color': '#ffffff' },
}

export const anchoragesLayer: FillLayerSpecification = {
  id: 'anchorages',
  type: 'fill',
  source: 'anchorages',
  'source-layer': 'anchorages',
  paint: {
    'fill-color': '#3d7f9e',
    'fill-opacity': 0.16,
    'fill-outline-color': '#1d4d64',
  },
}

export const visitorOnlyFilter: FilterSpecification = ['==', ['get', 'visitor'], true]

export function boatFilter(draft?: number, loa?: number): FilterSpecification | null {
  const clauses: ExpressionSpecification[] = []
  if (draft !== undefined) {
    clauses.push([
      'any',
      ['!', ['has', 'max_draft_m']],
      ['>=', ['coalesce', ['get', 'max_draft_m'], ['get', 'depth_m'], 99], draft],
    ])
  }
  if (loa !== undefined) {
    clauses.push([
      'any',
      ['!', ['has', 'max_loa_m']],
      ['>=', ['coalesce', ['get', 'max_loa_m'], 999], loa],
    ])
  }
  if (clauses.length === 0) return null
  return ['all', ...clauses]
}

export function kindFilter(kinds: readonly string[]): FilterSpecification | null {
  if (kinds.length === 0) return null
  return ['in', ['get', 'kind'], ['literal', [...kinds]]]
}

export function combineFilters(
  ...filters: (FilterSpecification | null)[]
): FilterSpecification | null {
  const present = filters.filter((filter): filter is ExpressionSpecification => Boolean(filter))
  if (present.length === 0) return null
  if (present.length === 1) return present[0] ?? null
  return ['all', ...present]
}
