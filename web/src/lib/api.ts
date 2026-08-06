/**
 * API client. Every call is offline-aware: it either serves cached data with a visible age or
 * fails loudly (docs/09 UX rule 4). No silent spinner over dead 4G.
 */
import type {
  CorrectionKind,
  FeatureCollection,
  HarbourDetail,
  HarbourList,
  IssueOut,
  NavAidDetail,
  SpotDetail,
  TargetType,
} from './types'
import { deviceToken } from './device'

export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/v1'

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly title: string,
    detail?: string,
  ) {
    super(detail ? `${title} — ${detail}` : title)
  }
}

export class OfflineError extends Error {
  constructor() {
    super('hors ligne')
  }
}

type Query = Record<string, string | number | boolean | undefined | null>

function url(path: string, query: Query = {}): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  }
  const qs = search.toString()
  return `${API_BASE}${path}${qs ? `?${qs}` : ''}`
}

async function request<T>(path: string, query: Query = {}, init: RequestInit = {}): Promise<T> {
  if (typeof navigator !== 'undefined' && navigator.onLine === false && !init.method) {
    // Let the service worker answer from cache; if it cannot, surface it as offline.
    try {
      return await send<T>(path, query, init)
    } catch {
      throw new OfflineError()
    }
  }
  return send<T>(path, query, init)
}

async function send<T>(path: string, query: Query, init: RequestInit): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  if (init.body) headers.set('Content-Type', 'application/json')
  const token = deviceToken()
  if (token) headers.set('X-Device-Token', token)

  const response = await fetch(url(path, query), { ...init, headers })
  if (response.status === 204) return undefined as T
  const payload = response.status === 304 ? undefined : await response.json().catch(() => undefined)
  if (!response.ok) {
    const problem = payload as { title?: string; detail?: string } | undefined
    throw new ApiError(response.status, problem?.title ?? 'Erreur', problem?.detail)
  }
  return payload as T
}

export const api = {
  spots: (params: {
    bbox: string
    kind?: string
    max_draft_m?: number
    max_loa_m?: number
    visitor?: boolean
    sheltered_from?: string
    sort?: 'distance' | 'price'
    limit?: number
  }) => request<FeatureCollection>('/spots', params),

  spot: (id: string) => request<SpotDetail>(`/spots/${id}`),

  harbours: (params: { q?: string; near?: string; limit?: number }) =>
    request<HarbourList>('/harbours', params),

  harbour: (slug: string) => request<HarbourDetail>(`/harbours/${slug}`),

  navaid: (id: string) => request<NavAidDetail>(`/navaids/${id}`),

  createDevice: () =>
    request<{ device_token: string }>('/devices', {}, { method: 'POST', body: '{}' }),

  /** v1's contribution loop: a correction to the referential (docs/08). */
  issue: (correction: {
    target: { type: TargetType; id: string }
    kind: CorrectionKind
    note: string
    position?: [number, number]
  }) =>
    request<IssueOut>(
      '/issues',
      {},
      {
        method: 'POST',
        body: JSON.stringify({
          target: correction.target,
          kind: correction.kind,
          note: correction.note,
          ...(correction.position ? { position: correction.position } : {}),
        }),
      },
    ),
}

export function tileUrl(layer: 'navaids' | 'spots' | 'anchorages'): string {
  return `${API_BASE}/tiles/${layer}/{z}/{x}/{y}.mvt`
}
