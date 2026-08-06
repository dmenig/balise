import { useAppStore } from '../app/store'
import { KIND_LABELS } from '../lib/format'
import type { SpotKind } from '../lib/types'

const KINDS: SpotKind[] = ['mooring_buoy', 'berth', 'anchorage']
const SECTORS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'] as const

/**
 * v1 filters the things v1 knows: kind, boat size, visitors, and shelter from tonight's wind
 * (docs/00). There is no "places libres" chip — offering one with no data behind it is exactly the
 * trap docs/06 says destroys the signal before it exists.
 *
 * Touch targets ≥ 56 px, one-hand reachable, no hover-only affordances (docs/09).
 */
export function FilterBar(): JSX.Element {
  const { filters, setFilters, resetFilters, theme, toggleTheme, seamarkOverlay, toggleSeamark } =
    useAppStore()

  const toggleKind = (kind: SpotKind) => {
    const next = filters.kinds.includes(kind)
      ? filters.kinds.filter((item) => item !== kind)
      : [...filters.kinds, kind]
    setFilters({ kinds: next })
  }

  const toggleSector = (sector: string) => {
    const next = filters.shelteredFrom.includes(sector)
      ? filters.shelteredFrom.filter((item) => item !== sector)
      : [...filters.shelteredFrom, sector]
    setFilters({ shelteredFrom: next })
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="flex gap-2 overflow-x-auto px-2 py-2" role="toolbar" aria-label="Filtres">
        <Chip
          pressed={filters.visitorOnly}
          onClick={() => setFilters({ visitorOnly: !filters.visitorOnly })}
          testId="filter-visitor"
        >
          Visiteurs
        </Chip>
        {KINDS.map((kind) => (
          <Chip
            key={kind}
            pressed={filters.kinds.includes(kind)}
            onClick={() => toggleKind(kind)}
            testId={`filter-kind-${kind}`}
          >
            {KIND_LABELS[kind]}
          </Chip>
        ))}
        <label className="flex shrink-0 items-center gap-1 rounded-full border border-sea-300 bg-white px-3 text-sm">
          <span className="whitespace-nowrap">Tirant d'eau</span>
          <input
            type="number"
            inputMode="decimal"
            step="0.1"
            min="0.3"
            max="10"
            value={filters.draft ?? ''}
            onChange={(event) =>
              setFilters({ draft: event.target.value ? Number(event.target.value) : undefined })
            }
            aria-label="Tirant d'eau du bateau en mètres"
            data-testid="filter-draft"
            className="h-touch w-16 bg-transparent text-right outline-none"
          />
          <span>m</span>
        </label>
        <label className="flex shrink-0 items-center gap-1 rounded-full border border-sea-300 bg-white px-3 text-sm">
          <span>Longueur</span>
          <input
            type="number"
            inputMode="decimal"
            step="0.5"
            min="2"
            max="60"
            value={filters.loa ?? ''}
            onChange={(event) =>
              setFilters({ loa: event.target.value ? Number(event.target.value) : undefined })
            }
            aria-label="Longueur hors tout du bateau en mètres"
            data-testid="filter-loa"
            className="h-touch w-16 bg-transparent text-right outline-none"
          />
          <span>m</span>
        </label>
        <Chip pressed={seamarkOverlay} onClick={toggleSeamark} testId="filter-seamark">
          Balisage OpenSeaMap
        </Chip>
        <Chip pressed={theme === 'night'} onClick={toggleTheme} testId="filter-night">
          Mode nuit
        </Chip>
        <button
          type="button"
          onClick={resetFilters}
          className="h-touch shrink-0 rounded-full px-3 text-sm underline"
        >
          Réinitialiser
        </button>
      </div>
      <div
        className="flex items-center gap-1 overflow-x-auto px-2 pb-2"
        role="group"
        aria-label="Abrité du vent de secteur"
      >
        <span className="shrink-0 text-xs text-sea-700">Abrité de&nbsp;:</span>
        {SECTORS.map((sector) => (
          <button
            key={sector}
            type="button"
            aria-pressed={filters.shelteredFrom.includes(sector)}
            data-testid={`filter-shelter-${sector}`}
            onClick={() => toggleSector(sector)}
            className={`h-11 w-11 shrink-0 rounded-full text-xs font-semibold ${
              filters.shelteredFrom.includes(sector)
                ? 'bg-sea-700 text-white'
                : 'border border-sea-300 bg-white text-sea-900'
            }`}
          >
            {sector}
          </button>
        ))}
      </div>
    </div>
  )
}

function Chip({
  pressed,
  onClick,
  children,
  testId,
}: {
  pressed: boolean
  onClick: () => void
  children: React.ReactNode
  testId: string
}): JSX.Element {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      data-testid={testId}
      onClick={onClick}
      className={`h-touch shrink-0 rounded-full px-4 text-sm font-medium ${
        pressed ? 'bg-sea-700 text-white' : 'border border-sea-300 bg-white text-sea-900'
      }`}
    >
      {children}
    </button>
  )
}
