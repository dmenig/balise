/** Map/UI state (Zustand). Server state lives in TanStack Query — no Redux ceremony (docs/09). */
import { create } from 'zustand'
import type { SpotKind } from '../lib/types'

export interface Filters {
  kinds: SpotKind[]
  visitorOnly: boolean
  draft?: number
  loa?: number
  /** Wind sectors to be sheltered from, e.g. ['NW']. A spot exposed to one of them is hidden. */
  shelteredFrom: string[]
}

export interface Viewport {
  lon: number
  lat: number
  zoom: number
}

export const DEFAULT_VIEWPORT: Viewport = { lon: -2.94, lat: 47.55, zoom: 12 }

interface AppState {
  filters: Filters
  viewport: Viewport
  theme: 'day' | 'night'
  seamarkOverlay: boolean
  selectedSpotId: string | null
  selectedNavAidId: string | null
  online: boolean
  /** The boat's position, client-side only: it is never sent to the server (docs/04). */
  position: [number, number] | null
  lastSyncAt: string | null
  queued: number
  setFilters: (patch: Partial<Filters>) => void
  resetFilters: () => void
  setViewport: (viewport: Viewport) => void
  toggleTheme: () => void
  toggleSeamark: () => void
  selectSpot: (id: string | null) => void
  selectNavAid: (id: string | null) => void
  setOnline: (online: boolean) => void
  setPosition: (position: [number, number] | null) => void
  setLastSyncAt: (at: string | null) => void
  setQueued: (count: number) => void
}

export const DEFAULT_FILTERS: Filters = {
  kinds: [],
  visitorOnly: false,
  shelteredFrom: [],
}

export const useAppStore = create<AppState>((set) => ({
  filters: DEFAULT_FILTERS,
  viewport: DEFAULT_VIEWPORT,
  theme: 'day',
  seamarkOverlay: false,
  selectedSpotId: null,
  selectedNavAidId: null,
  online: typeof navigator === 'undefined' ? true : navigator.onLine,
  position: null,
  lastSyncAt: null,
  queued: 0,
  setFilters: (patch) => set((state) => ({ filters: { ...state.filters, ...patch } })),
  resetFilters: () => set({ filters: DEFAULT_FILTERS }),
  setViewport: (viewport) => set({ viewport }),
  toggleTheme: () => set((state) => ({ theme: state.theme === 'day' ? 'night' : 'day' })),
  toggleSeamark: () => set((state) => ({ seamarkOverlay: !state.seamarkOverlay })),
  selectSpot: (id) => set({ selectedSpotId: id, selectedNavAidId: null }),
  selectNavAid: (id) => set({ selectedNavAidId: id, selectedSpotId: null }),
  setOnline: (online) => set({ online }),
  setPosition: (position) => set({ position }),
  setLastSyncAt: (at) => set({ lastSyncAt: at }),
  setQueued: (count) => set({ queued: count }),
}))

export function bboxOf(viewport: Viewport, spanDeg = 0.3): string {
  const half = spanDeg / 2
  const lonSpan = half / Math.max(Math.cos((viewport.lat * Math.PI) / 180), 0.2)
  return [
    (viewport.lon - lonSpan).toFixed(4),
    (viewport.lat - half).toFixed(4),
    (viewport.lon + lonSpan).toFixed(4),
    (viewport.lat + half).toFixed(4),
  ].join(',')
}
