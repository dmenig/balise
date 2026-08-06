import { useQuery } from '@tanstack/react-query'
import { api } from '../../lib/api'
import { useAppStore } from '../../app/store'

/** "What is this red thing in the water?" — the P5 persona, and the SEO engine (docs/02, docs/09). */
export function NavAidSheet({ navAidId }: { navAidId: string }): JSX.Element {
  const close = useAppStore((state) => state.selectNavAid)
  const { data, isLoading } = useQuery({
    queryKey: ['navaid', navAidId],
    queryFn: () => api.navaid(navAidId),
    staleTime: 24 * 60 * 60 * 1000,
  })

  return (
    <section
      data-testid="navaid-sheet"
      aria-labelledby="navaid-title"
      className="max-h-full overflow-y-auto rounded-t-2xl bg-white p-4 shadow-2xl"
    >
      <div className="flex items-start justify-between">
        <h2 id="navaid-title" className="text-lg font-semibold text-sea-900">
          {data?.label ?? 'Chargement…'}
          {data?.name ? ` — ${data.name}` : ''}
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
      {isLoading && <p className="mt-2 text-sm">Chargement…</p>}
      {data && (
        <>
          <p className="mt-2 text-sm text-sea-900">{data.explainer}</p>
          <dl className="mt-3 grid grid-cols-2 gap-y-1 text-sm">
            {data.colour && <Row label="Couleur" value={data.colour} />}
            {data.colour_pattern && <Row label="Motif" value={data.colour_pattern} />}
            {data.shape && <Row label="Forme" value={data.shape} />}
            {data.topmark && <Row label="Voyant" value={data.topmark} />}
            {data.light && (
              <Row label="Feu" value={`${data.light.text} — ${data.light.character ?? ''}`} />
            )}
            {data.height_m != null && <Row label="Hauteur" value={`${data.height_m} m`} />}
          </dl>
          <p className="mt-3 text-xs text-sea-700">
            Cette marque ne se « libère » pas : c'est un repère de balisage, pas une place.
          </p>
          <p className="mt-2 text-[11px] text-sea-500">{data.source}</p>
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
