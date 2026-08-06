/**
 * Nav aids use official IALA region A symbology (docs/09): a sailor must recognise a cardinal
 * mark instantly. Colours and topmark shapes are non-negotiable, so they are derived from the
 * S-57 attributes carried in the tile, never invented per-app.
 */
import type {
  CircleLayerSpecification,
  ExpressionSpecification,
  SymbolLayerSpecification,
} from 'maplibre-gl'

export const IALA_COLOURS = {
  red: '#d62828',
  green: '#1b7f3b',
  yellow: '#f4c20d',
  black: '#1b1b1b',
  white: '#f8f8f8',
  blue: '#1d4d64',
} as const

/** `nav_aid.colour` is stored as decoded French labels ("rouge", "noir, jaune"). */
export const navAidColour: ExpressionSpecification = [
  'case',
  ['in', 'rouge', ['coalesce', ['get', 'colour'], '']],
  IALA_COLOURS.red,
  ['in', 'vert', ['coalesce', ['get', 'colour'], '']],
  IALA_COLOURS.green,
  ['in', 'jaune', ['coalesce', ['get', 'colour'], '']],
  IALA_COLOURS.yellow,
  ['in', 'noir', ['coalesce', ['get', 'colour'], '']],
  IALA_COLOURS.black,
  IALA_COLOURS.white,
]

const BEACON_CLASSES = ['bcnlat', 'bcncar', 'bcnisd', 'bcnsaw', 'bcnspp']

/** Beacons are fixed (square marker), buoys float (round marker) — the chart convention. */
export const navAidShape: ExpressionSpecification = [
  'case',
  ['in', ['get', 's57_class'], ['literal', BEACON_CLASSES]],
  'square',
  'circle',
]

export const navAidsLayer: CircleLayerSpecification = {
  id: 'navaids',
  type: 'circle',
  source: 'navaids',
  'source-layer': 'navaids',
  minzoom: 11,
  paint: {
    'circle-radius': ['interpolate', ['linear'], ['zoom'], 11, 2.5, 14, 5, 17, 8],
    'circle-color': navAidColour,
    'circle-stroke-width': 1,
    'circle-stroke-color': '#0b2b3c',
  },
}

export const navAidLabelsLayer: SymbolLayerSpecification = {
  id: 'navaids-labels',
  type: 'symbol',
  source: 'navaids',
  'source-layer': 'navaids',
  minzoom: 14,
  layout: {
    'text-field': ['coalesce', ['get', 'name'], ''],
    'text-size': 10,
    'text-offset': [0, 1.1],
    'text-anchor': 'top',
    'text-optional': true,
  },
  paint: {
    'text-color': '#0b2b3c',
    'text-halo-color': '#ffffff',
    'text-halo-width': 1.2,
  },
}

/** A lit mark gets a halo so it reads at a glance at night. */
export const navAidLitLayer: CircleLayerSpecification = {
  id: 'navaids-lit',
  type: 'circle',
  source: 'navaids',
  'source-layer': 'navaids',
  minzoom: 12,
  filter: ['==', ['get', 'lit'], true],
  paint: {
    'circle-radius': ['interpolate', ['linear'], ['zoom'], 12, 6, 17, 16],
    'circle-color': IALA_COLOURS.yellow,
    'circle-opacity': 0.18,
  },
}
