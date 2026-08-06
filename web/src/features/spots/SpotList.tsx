import { KIND_LABELS, distanceNm, spotSubtitle } from '../../lib/format'
import { useAppStore } from '../../app/store'
import { useSpotsInView } from './useSpotsInView'

/**
 * The list is not a nicety: the map must never be the only way to reach data (docs/09
 * accessibility). It is also how a sailor scans candidates without pinching a map on a moving boat.
 */
export function SpotList(): JSX.Element {
  const selectSpot = useAppStore((state) => state.selectSpot)
  const position = useAppStore((state) => state.position)
  const { data, isLoading, error } = useSpotsInView()

  if (isLoading) return <p className="px-3 py-2 text-sm text-sea-700">Recherche…</p>
  if (error)
    return (
      <p className="px-3 py-2 text-sm text-sea-700" role="alert">
        Liste indisponible hors ligne — la carte téléchargée reste lisible.
      </p>
    )

  return (
    <div className="max-h-[30vh] overflow-y-auto bg-white">
      <ul>
        {data?.features.map((feature) => (
          <li key={feature.id}>
            <button
              type="button"
              data-testid="spot-list-item"
              data-spot-id={feature.id}
              onClick={() => selectSpot(feature.id)}
              className="flex min-h-touch w-full items-center justify-between gap-2 border-b border-sea-100 px-3 py-2 text-left"
            >
              <span>
                <span className="block text-sm font-medium text-sea-900">
                  {KIND_LABELS[feature.properties.kind] ?? feature.properties.kind}
                  {feature.properties.code ? ` ${feature.properties.code}` : ''}
                  {feature.properties.harbour_name ? ` · ${feature.properties.harbour_name}` : ''}
                </span>
                <span className="block text-xs text-sea-700">
                  {spotSubtitle(
                    feature.properties,
                    position
                      ? distanceNm(position, feature.geometry.coordinates as [number, number])
                      : undefined,
                  )}
                </span>
              </span>
            </button>
          </li>
        ))}
      </ul>
      {data && <p className="px-3 py-2 text-[11px] text-sea-500">{data.attribution.join(' — ')}</p>}
    </div>
  )
}
