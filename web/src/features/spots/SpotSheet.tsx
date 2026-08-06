import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../../lib/api'
import { KIND_LABELS, clock, compass, knots, metres, price } from '../../lib/format'
import { StatusBadge } from '../../components/StatusBadge'
import { CorrectionForm } from '../corrections/CorrectionForm'
import { useAppStore } from '../../app/store'

/**
 * The escale decision sheet (docs/02). In v1 it answers "where can I stop" and "does my boat fit",
 * and answers "is it free" the honest way: the capitainerie's phone and VHF, one tap away
 * (docs/00). The status slot is present and reserved, so v2 adds a live chip without reflowing it.
 */
export function SpotSheet({ spotId }: { spotId: string }): JSX.Element {
  const close = useAppStore((state) => state.selectSpot)
  const [correcting, setCorrecting] = useState(false)

  const { data, isLoading, error } = useQuery({
    queryKey: ['spot', spotId],
    queryFn: () => api.spot(spotId),
    staleTime: 60_000,
  })

  return (
    <section
      data-testid="spot-sheet"
      data-spot-id={spotId}
      aria-labelledby="spot-title"
      className="max-h-full overflow-y-auto rounded-t-2xl bg-white p-4 shadow-2xl"
    >
      <div className="flex items-start justify-between gap-2">
        <h2 id="spot-title" className="text-lg font-semibold text-sea-900">
          {data
            ? `${KIND_LABELS[data.kind] ?? data.kind}${data.code ? ` ${data.code}` : ''}`
            : 'Chargement…'}
        </h2>
        <button
          type="button"
          onClick={() => close(null)}
          aria-label="Fermer la fiche"
          className="h-touch w-touch rounded-full text-2xl leading-none text-sea-700"
        >
          ×
        </button>
      </div>

      {isLoading && <p className="mt-3 text-sm text-sea-700">Chargement de la fiche…</p>}
      {error && (
        <p className="mt-3 text-sm text-sea-700" role="alert">
          Fiche indisponible hors ligne. Réessayez à la reconnexion.
        </p>
      )}

      {data && (
        <>
          {/* Reserved status slot (docs/09): `null` today, a live chip in v2, same layout. */}
          <div className="mt-3 min-h-[34px]">
            <StatusBadge status={data.properties.status} />
          </div>

          <dl className="mt-4 grid grid-cols-2 gap-y-2 text-sm">
            <Row label="Profondeur (carte)" value={metres(data.properties.depth_m)} />
            <Row
              label="Profondeur à la BM"
              value={
                data.tide?.depth_at_next_low_water_m != null
                  ? `${data.tide.depth_at_next_low_water_m.toFixed(1)} m (estimation)`
                  : '—'
              }
            />
            <Row label="LOA max" value={metres(data.properties.max_loa_m)} />
            <Row label="Tirant d'eau max" value={metres(data.properties.max_draft_m)} />
            <Row label="Tenue" value={data.properties.holding ?? '—'} />
            <Row
              label="Exposé"
              value={data.properties.exposure.length ? data.properties.exposure.join(', ') : '—'}
            />
            <Row label="Tarif" value={price(data.properties.price_per_night_cents)} />
            <Row label="Visiteurs" value={data.properties.visitor ? 'oui' : '—'} />
          </dl>

          {data.tide && (
            <p className="mt-3 text-sm text-sea-700">
              {data.tide.next_high_water && (
                <>
                  PM {clock(data.tide.next_high_water.at)} ({data.tide.next_high_water.height_m} m)
                </>
              )}
              {data.tide.next_low_water && (
                <>
                  {' '}
                  · BM {clock(data.tide.next_low_water.at)} ({data.tide.next_low_water.height_m} m)
                </>
              )}
              {data.tide.next_high_water?.coefficient && (
                <> · coeff. {data.tide.next_high_water.coefficient}</>
              )}
            </p>
          )}

          {data.weather?.points[0] && (
            <p className="mt-1 text-sm text-sea-700">
              Vent {knots(data.weather.points[0].wind_kt)}{' '}
              {compass(data.weather.points[0].wind_dir_deg)}
              {data.weather.points[0].gust_kt != null && (
                <> · rafales {knots(data.weather.points[0].gust_kt)}</>
              )}
              {data.weather.points[0].wave_m != null && (
                <> · mer {data.weather.points[0].wave_m} m</>
              )}
            </p>
          )}

          {data.harbour && (
            <div className="mt-4 rounded-xl bg-sea-50 p-3 text-sm">
              <p className="font-medium text-sea-900">{data.harbour.name}</p>
              <p className="text-sea-700">
                {data.harbour.vhf_channel ? `VHF ${data.harbour.vhf_channel}` : 'VHF —'}
                {data.harbour.opening_hours ? ` · ${data.harbour.opening_hours}` : ''}
              </p>
              <div className="mt-2 flex gap-2">
                {data.harbour.phone && (
                  <a
                    href={`tel:${data.harbour.phone}`}
                    data-testid="call-harbour"
                    className="flex h-touch flex-1 items-center justify-center rounded-xl bg-sea-700 px-3 font-semibold text-white"
                  >
                    Appeler la capitainerie
                  </a>
                )}
                <a
                  href={`geo:${data.position[1]},${data.position[0]}`}
                  className="flex h-touch flex-1 items-center justify-center rounded-xl border-2 border-sea-700 px-3 font-semibold text-sea-900"
                >
                  Y aller
                </a>
              </div>
            </div>
          )}

          {correcting ? (
            <CorrectionForm
              target={{ type: 'spot', id: spotId }}
              onDone={() => setCorrecting(false)}
            />
          ) : (
            <button
              type="button"
              data-testid="report-correction"
              onClick={() => setCorrecting(true)}
              className="mt-4 h-touch w-full rounded-xl border-2 border-sea-700 text-sm font-semibold text-sea-900"
            >
              Signaler une erreur sur cette place
            </button>
          )}

          <ul className="mt-4 space-y-1 text-xs text-sea-700">
            {data.warnings.map((warning) => (
              <li key={warning}>⚠ {warning}</li>
            ))}
          </ul>
          <p className="mt-2 text-[11px] text-sea-500">{data.attribution.join(' — ')}</p>
        </>
      )}
    </section>
  )
}

function Row({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <>
      <dt className="text-sea-700">{label}</dt>
      <dd className="text-right font-medium text-sea-900">{value}</dd>
    </>
  )
}
