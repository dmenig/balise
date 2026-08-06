import { Suspense, lazy, useState } from 'react'
import { Link } from 'react-router-dom'
import { FilterBar } from '../components/FilterBar'
import { OfflineBanner } from '../components/OfflineBanner'
import { DisclaimerGate, DisclaimerStrip } from '../components/DisclaimerStrip'
import { SearchBox } from '../features/harbours/SearchBox'
import { SpotList } from '../features/spots/SpotList'
import { useSpotsInView } from '../features/spots/useSpotsInView'
import { SpotSheet } from '../features/spots/SpotSheet'
import { NavAidSheet } from '../features/navaids/NavAidSheet'
import { DownloadArea } from '../features/offline/DownloadArea'
import { useAppStore } from './store'

const MapView = lazy(() => import('../map/MapView').then((module) => ({ default: module.MapView })))

/**
 * The map is the product, so the map gets the screen (docs/09). Search and filters collapse into a
 * single row, and the list is a bottom sheet the sailor pulls up — primary actions stay in the
 * bottom third, reachable one-handed.
 */
export function MapScreen(): JSX.Element {
  const selectedSpotId = useAppStore((state) => state.selectedSpotId)
  const selectedNavAidId = useAppStore((state) => state.selectedNavAidId)
  const [listOpen, setListOpen] = useState(true)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const sheetOpen = Boolean(selectedSpotId ?? selectedNavAidId)

  return (
    <div className="flex h-full flex-col">
      <DisclaimerStrip />
      <OfflineBanner />

      <div className="flex items-center gap-1 px-2 pt-1">
        <div className="min-w-0 flex-1">
          <SearchBox />
        </div>
        <button
          type="button"
          aria-expanded={filtersOpen}
          data-testid="toggle-filters"
          onClick={() => setFiltersOpen((open) => !open)}
          className={`h-touch shrink-0 rounded-xl px-3 text-sm font-semibold ${
            filtersOpen ? 'bg-sea-700 text-white' : 'border border-sea-300 bg-white text-sea-900'
          }`}
        >
          Filtres
        </button>
      </div>
      {filtersOpen && <FilterBar />}

      <div className="relative min-h-[40vh] flex-1" data-testid="map-area">
        <Suspense fallback={<p className="p-4 text-sm">Chargement de la carte…</p>}>
          <MapView />
        </Suspense>
        {sheetOpen && (
          <div className="absolute inset-x-0 bottom-0 z-30 max-h-full overflow-y-auto">
            {selectedSpotId && <SpotSheet spotId={selectedSpotId} />}
            {selectedNavAidId && <NavAidSheet navAidId={selectedNavAidId} />}
          </div>
        )}
      </div>

      {!sheetOpen && (
        <div className="border-t border-sea-100 bg-white">
          <button
            type="button"
            aria-expanded={listOpen}
            data-testid="toggle-list"
            onClick={() => setListOpen((open) => !open)}
            className="flex min-h-touch w-full items-center justify-between px-3 text-sm font-semibold text-sea-900"
          >
            <SpotListSummary />
            <span aria-hidden="true">{listOpen ? '▾' : '▴'}</span>
          </button>
          {listOpen && (
            <>
              <SpotList />
              <DownloadArea />
              <footer className="flex flex-wrap gap-3 px-3 py-2 text-xs text-sea-700">
                <Link to="/contribuer" className="underline">
                  Contribuer
                </Link>
                <Link to="/mes-escales" className="underline">
                  Mes escales
                </Link>
                <Link to="/donnees" className="underline">
                  Données
                </Link>
                <Link to="/cgu" className="underline">
                  CGU
                </Link>
                <Link to="/a-propos" className="underline">
                  À propos
                </Link>
              </footer>
            </>
          )}
        </div>
      )}
      <DisclaimerGate />
    </div>
  )
}

/** One query, two readers: the handle can never disagree with the rows underneath it. */
function SpotListSummary(): JSX.Element {
  const { data, isLoading } = useSpotsInView()
  const total = data?.features.length ?? 0
  return (
    <span data-testid="free-count">
      {isLoading
        ? 'Recherche…'
        : `${total} place${total > 1 ? 's' : ''} recensée${total > 1 ? 's' : ''} dans la vue`}
    </span>
  )
}
