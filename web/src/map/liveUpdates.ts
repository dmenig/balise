/**
 * The client data layer's live-update seam (docs/08, docs/09 S5).
 *
 * Components subscribe to a bbox and do not know whether updates are live. In v1 the implementation
 * is a no-op: it never calls back, so nothing ever calls `setFeatureState` and every spot stays
 * neutral. In v2 the same interface is backed by the websocket with `/status` polling as fallback.
 */
import type { Map as MapLibreMap } from 'maplibre-gl'
import type { SpotState } from '../lib/types'

export interface StatusUpdate {
  spotId: number
  state: SpotState
  confidence: number
}

export type Unsubscribe = () => void

export interface LiveUpdates {
  subscribe(bbox: string, onUpdate: (update: StatusUpdate) => void): Unsubscribe
}

/** v1. There are no updates, so there is nothing to subscribe to. */
export const noLiveUpdates: LiveUpdates = {
  subscribe() {
    return () => undefined
  },
}

/**
 * v2 only. Kept here so the join is written once, next to the interface it belongs to, and so the
 * paint expressions' `feature-state` branch has exactly one writer.
 */
export function applyStatus(map: MapLibreMap, update: StatusUpdate): void {
  map.setFeatureState(
    { source: 'spots', sourceLayer: 'spots', id: update.spotId },
    { state: update.state, confidence: update.confidence },
  )
}
