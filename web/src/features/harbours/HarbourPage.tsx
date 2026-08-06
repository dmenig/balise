import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { api } from '../../lib/api'
import { KIND_LABELS, SOURCE_LABELS, ageLabel, price } from '../../lib/format'

const SERVICE_LABELS: Record<string, string> = {
  water: 'Eau',
  fuel: 'Carburant',
  electricity: 'Électricité',
  showers: 'Douches',
  waste: 'Déchets',
  pump_out: 'Eaux noires',
  careening: 'Aire de carénage',
  slipway: 'Cale de mise à l’eau',
  wifi: 'Wi-Fi',
  laundry: 'Laverie',
  provisions: 'Avitaillement',
  restaurant: 'Restaurant',
  harbour_office: 'Capitainerie',
  visitor_berth: 'Places visiteurs',
  visitor_mooring: 'Corps-morts visiteurs',
  boat_lift: 'Grue / élévateur',
  boat_hoist: 'Portique',
  mechanic: 'Mécanicien',
  boatyard: 'Chantier',
  nautical_club: 'Club nautique',
  chandler: 'Shipchandler',
  parking: 'Parking',
  toilets: 'Sanitaires',
}

/** Prerendered at build time for SEO — readable with JavaScript disabled (ADR-0001). */
export function HarbourPage(): JSX.Element {
  const { slug = '' } = useParams()
  const { data, isLoading, error } = useQuery({
    queryKey: ['harbour', slug],
    queryFn: () => api.harbour(slug),
    staleTime: 5 * 60 * 1000,
  })

  if (isLoading) return <p className="p-4">Chargement du port…</p>
  if (error || !data)
    return (
      <div className="p-4">
        <p role="alert">Port introuvable ou hors ligne.</p>
        <Link to="/" className="underline">
          Retour à la carte
        </Link>
      </div>
    )

  return (
    <article className="mx-auto max-w-2xl p-4">
      <nav className="text-sm">
        <Link to="/" className="underline">
          Carte
        </Link>{' '}
        / <span>{data.name}</span>
      </nav>
      <h1 className="mt-2 text-2xl font-semibold text-sea-900">{data.name}</h1>
      <p className="mt-1 text-sm text-sea-700">
        {data.spot_count} place{data.spot_count > 1 ? 's' : ''} recensée
        {data.spot_count > 1 ? 's' : ''}. La disponibilité n'est pas connue : appelez la
        capitainerie{data.vhf_channel ? ` ou passez sur le canal VHF ${data.vhf_channel}` : ''}.
      </p>

      <dl className="mt-4 grid grid-cols-2 gap-y-1 text-sm">
        {data.vhf_channel && <Row label="VHF" value={`canal ${data.vhf_channel}`} />}
        {data.phone && <Row label="Téléphone" value={data.phone} />}
        {data.opening_hours && <Row label="Horaires" value={data.opening_hours} />}
        {data.website && <Row label="Site" value={data.website} />}
      </dl>

      {data.phone && (
        <a
          href={`tel:${data.phone}`}
          className="mt-3 flex h-touch items-center justify-center rounded-xl bg-sea-700 font-semibold text-white"
        >
          Appeler la capitainerie
        </a>
      )}

      {data.services.length > 0 && (
        <>
          <h2 className="mt-6 text-lg font-semibold text-sea-900">Services</h2>
          <ul className="mt-1 flex flex-wrap gap-2 text-sm">
            {data.services.map((service) => (
              <li key={service} className="rounded-full bg-sea-50 px-3 py-1">
                {SERVICE_LABELS[service] ?? service}
              </li>
            ))}
          </ul>
        </>
      )}

      <h2 className="mt-6 text-lg font-semibold text-sea-900">Zones et pannes</h2>
      <ul className="mt-1 divide-y divide-sea-100 text-sm">
        {data.fields.map((field) => (
          <li key={field.id} className="py-2">
            <p className="font-medium text-sea-900">
              {field.name ?? KIND_LABELS[field.kind] ?? field.kind}
            </p>
            <p className="text-sea-700">
              {field.capacity != null ? `${field.capacity} places` : 'capacité inconnue'}
              {field.visitor_capacity != null ? ` · ${field.visitor_capacity} visiteurs` : ''}
              {field.price_per_night_cents != null
                ? ` · ${price(field.price_per_night_cents)}`
                : ''}
            </p>
            {field.status?.free != null && field.status.source_kind && (
              <p className="text-sea-700">
                {field.status.free} libre(s) — {SOURCE_LABELS[field.status.source_kind]}
                {field.status.as_of
                  ? `, ${ageLabel(Math.max((Date.now() - new Date(field.status.as_of).getTime()) / 1000, 0))}`
                  : ''}
              </p>
            )}
            {field.price_note && <p className="text-xs text-sea-500">{field.price_note}</p>}
          </li>
        ))}
        {data.fields.length === 0 && <li className="py-2 text-sea-700">Aucune zone recensée.</li>}
      </ul>

      <p className="mt-6 text-xs text-sea-700">{data.disclaimer}</p>
      <p className="mt-1 text-[11px] text-sea-500">{data.attribution.join(' — ')}</p>
    </article>
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
