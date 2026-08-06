import { SOURCE_LABELS, ageLabel, stateIcon } from '../lib/format'
import type { Status } from '../lib/types'

const TONE: Record<string, string> = {
  free: 'bg-free text-white',
  'free-soft': 'border-2 border-free bg-white text-free',
  occupied: 'bg-occupied text-white',
  unknown: 'border border-sea-300 bg-sea-50 text-sea-700',
}

/**
 * The status slot. `status === null` is the v1 rendering *and* the v2 rendering for any spot nobody
 * has reported (docs/09), so this branch is never dead code — and the slot exists in v1 so adding a
 * live chip in v2 does not reflow the sheet.
 *
 * In v1 it says what is true: we do not know, here is the harbour's phone number.
 */
export function StatusBadge({ status }: { status: Status | null }): JSX.Element {
  if (status === null || status.state === 'unknown') {
    return (
      <span
        data-testid="status-badge"
        data-state="unknown"
        className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm font-medium ${TONE.unknown}`}
      >
        <span aria-hidden="true">?</span>
        <span>Disponibilité inconnue</span>
      </span>
    )
  }

  const tone =
    status.state === 'free'
      ? status.bucket === 'confirmed'
        ? TONE.free
        : TONE['free-soft']
      : status.state === 'occupied'
        ? TONE.occupied
        : TONE.unknown

  const headline =
    status.state === 'free'
      ? status.bucket === 'confirmed'
        ? 'Libre'
        : 'Probablement libre'
      : status.state === 'occupied'
        ? 'Occupé'
        : 'Hors service'

  return (
    <span
      data-testid="status-badge"
      data-state={status.state}
      data-bucket={status.bucket}
      className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm font-semibold ${tone}`}
    >
      <span aria-hidden="true">{stateIcon(status.state)}</span>
      <span>{headline}</span>
      {status.source_kind !== null && status.age_seconds !== null && (
        <span className="text-xs font-normal opacity-90">
          {SOURCE_LABELS[status.source_kind]}, {ageLabel(status.age_seconds)}
        </span>
      )}
    </span>
  )
}
