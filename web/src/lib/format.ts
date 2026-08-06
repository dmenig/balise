/** Sailor units, always: nautical miles, metres, knots. Never km/h (docs/09 UX rule 6). */
import type { ConfidenceBucket, SourceKind, SpotState, Status } from './types'

export const SOURCE_LABELS: Record<SourceKind, string> = {
  port_feed: 'Port',
  sensor: 'Capteur',
  community: 'Communauté',
  ais: 'AIS',
  manual: 'Balise',
  import: 'Référentiel',
}

export const STATE_LABELS: Record<SpotState, string> = {
  free: 'Libre',
  occupied: 'Occupé',
  reserved: 'Réservé',
  out_of_service: 'Hors service',
  unknown: 'Disponibilité inconnue',
}

export function ageLabel(seconds: number): string {
  if (seconds < 60) return "à l'instant"
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `il y a ${minutes} min`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `il y a ${hours} h`
  const days = Math.round(hours / 24)
  return `il y a ${days} j`
}

/** The honesty string: never a state without its source and its age (docs/06). */
export function statusLabel(status: Status | null): string {
  // `null` is v1's answer and v2's answer for an unreported spot: nothing to attribute or date.
  if (
    status === null ||
    status.state === 'unknown' ||
    status.source_kind === null ||
    status.age_seconds === null
  ) {
    return STATE_LABELS.unknown
  }
  const prefix =
    status.state === 'free' && status.bucket === 'probable'
      ? 'Probablement libre'
      : STATE_LABELS[status.state]
  return `${prefix} — ${SOURCE_LABELS[status.source_kind]}, ${ageLabel(status.age_seconds)}`
}

export function bucketClass(bucket: ConfidenceBucket, state: SpotState): string {
  if (state === 'unknown') return 'pin-unknown'
  if (state === 'occupied') return 'pin-occupied'
  return bucket === 'confirmed' ? 'pin-free' : 'pin-free-soft'
}

export function stateIcon(state: SpotState): string {
  if (state === 'free') return '✓'
  if (state === 'occupied') return '●'
  return '?'
}

export function nauticalMiles(metres: number): string {
  return `${(metres / 1852).toFixed(1)} NM`
}

export function metres(value: number | null): string {
  return value === null ? '—' : `${value.toFixed(1)} m`
}

export function knots(value: number | null): string {
  return value === null ? '—' : `${Math.round(value)} kt`
}

export function price(cents: number | null): string {
  return cents === null ? '—' : `${(cents / 100).toFixed(2)} €/nuit`
}

const COMPASS = [
  'N',
  'NNE',
  'NE',
  'ENE',
  'E',
  'ESE',
  'SE',
  'SSE',
  'S',
  'SSW',
  'SW',
  'WSW',
  'W',
  'WNW',
  'NW',
  'NNW',
]

export function compass(degrees: number | null): string {
  if (degrees === null) return '—'
  return COMPASS[Math.round(degrees / 22.5) % 16] ?? '—'
}

export function clock(iso: string): string {
  return new Date(iso).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
}

export function cacheAge(iso: string | null): string | null {
  if (!iso) return null
  const date = new Date(iso)
  return `données du ${date.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit' })} à ${clock(iso)}`
}

/**
 * The list row's subtitle. In v1 it describes the *object* — kind, depth, size limits — because
 * that is what we know; the status line arrives in v2 without changing the layout (docs/09).
 */
const METRES_PER_NM = 1852

/**
 * Great-circle distance in nautical miles (docs/09 rule 6), computed here and not asked of the API:
 * the boat's position never leaves the browser (docs/04).
 */
export function distanceNm(from: [number, number], to: [number, number]): number {
  const [lon1, lat1] = from
  const [lon2, lat2] = to
  const radius = 6_371_000
  const toRad = (degrees: number) => (degrees * Math.PI) / 180
  const dLat = toRad(lat2 - lat1)
  const dLon = toRad(lon2 - lon1)
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2
  return (2 * radius * Math.asin(Math.sqrt(a))) / METRES_PER_NM
}

export function formatDistanceNm(nm: number): string {
  return nm < 1 ? `${nm.toFixed(2)} NM` : `${nm.toFixed(1)} NM`
}

export function spotSubtitle(
  properties: {
    kind: string
    depth_m: number | null
    max_loa_m: number | null
    max_draft_m: number | null
    visitor: boolean
    status: Status | null
  },
  distance?: number,
): string {
  if (properties.status !== null) return statusLabel(properties.status)
  // The title already carries the kind, so the subtitle carries what distinguishes this spot.
  const parts: string[] = []
  if (distance !== undefined) parts.push(formatDistanceNm(distance))
  if (properties.depth_m !== null) parts.push(`${properties.depth_m.toFixed(1)} m de sonde`)
  if (properties.max_draft_m !== null) parts.push(`TE ≤ ${properties.max_draft_m.toFixed(1)} m`)
  if (properties.max_loa_m !== null) parts.push(`LOA ≤ ${properties.max_loa_m.toFixed(0)} m`)
  if (properties.visitor) parts.push('visiteurs')
  return parts.length ? parts.join(' · ') : 'Dimensions non renseignées'
}

export const KIND_LABELS: Record<string, string> = {
  mooring_buoy: 'Bouée de mouillage',
  berth: 'Place de port',
  anchorage: 'Mouillage',
  pile: 'Pieu',
  quay: 'Quai',
}
