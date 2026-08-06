/**
 * Base style: a muted "sea chart" look (land beige, sea pale blue) built from raster OSM tiles,
 * plus the optional OpenSeaMap seamark overlay for users who want the full chart look (docs/09).
 *
 * A self-hosted PMTiles vector basemap can replace `VITE_BASEMAP_URL` without touching anything
 * else — the overlay layers only depend on our own MVT sources.
 */
import type { StyleSpecification } from 'maplibre-gl'
import { tileUrl } from '../lib/api'

const OSM_RASTER = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
const SEAMARK_RASTER = 'https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png'

export const ATTRIBUTION =
  'Fonds de carte © OpenStreetMap contributors (ODbL) — Balisage : Shom, 2026 (Licence Ouverte 2.0)'

export interface StyleOptions {
  basemapUrl?: string
  night?: boolean
}

export function buildStyle({ basemapUrl, night = false }: StyleOptions = {}): StyleSpecification {
  return {
    version: 8,
    glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
    sources: {
      basemap: {
        type: 'raster',
        tiles: [basemapUrl ?? OSM_RASTER],
        tileSize: 256,
        maxzoom: 19,
        attribution: ATTRIBUTION,
      },
      seamark: {
        type: 'raster',
        tiles: [SEAMARK_RASTER],
        tileSize: 256,
        maxzoom: 18,
        attribution: 'Seamarks © OpenSeaMap (ODbL)',
      },
      navaids: { type: 'vector', tiles: [absolute(tileUrl('navaids'))], minzoom: 8, maxzoom: 16 },
      spots: { type: 'vector', tiles: [absolute(tileUrl('spots'))], minzoom: 10, maxzoom: 18 },
      anchorages: {
        type: 'vector',
        tiles: [absolute(tileUrl('anchorages'))],
        minzoom: 10,
        maxzoom: 18,
      },
    },
    layers: [
      {
        id: 'sea',
        type: 'background',
        paint: { 'background-color': night ? '#0d0000' : '#dceaf2' },
      },
      {
        id: 'basemap',
        type: 'raster',
        source: 'basemap',
        paint: {
          // Muted, and in night mode dimmed to near-nothing so no white light is emitted.
          'raster-saturation': night ? -1 : -0.4,
          'raster-brightness-max': night ? 0.25 : 0.95,
          'raster-opacity': night ? 0.35 : 0.9,
        },
      },
      {
        id: 'seamark',
        type: 'raster',
        source: 'seamark',
        layout: { visibility: 'none' },
        paint: { 'raster-opacity': 0.9 },
      },
    ],
  }
}

function absolute(path: string): string {
  if (path.startsWith('http')) return path
  if (typeof window === 'undefined') return path
  return `${window.location.origin}${path}`
}
