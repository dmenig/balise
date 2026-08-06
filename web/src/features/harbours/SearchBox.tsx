import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'

export function SearchBox(): JSX.Element {
  const [term, setTerm] = useState('')
  const enabled = term.trim().length >= 2
  const { data } = useQuery({
    queryKey: ['harbour-search', term],
    queryFn: () => api.harbours({ q: term.trim(), limit: 8 }),
    enabled,
    staleTime: 60_000,
  })

  return (
    <div className="relative px-2 py-1">
      <input
        type="search"
        value={term}
        onChange={(event) => setTerm(event.target.value)}
        placeholder="Rechercher un port, une commune…"
        aria-label="Rechercher un port"
        data-testid="harbour-search"
        className="h-touch w-full rounded-xl border border-sea-300 px-3 text-base"
      />
      {enabled && data && data.harbours.length > 0 && (
        <ul className="absolute left-2 right-2 z-20 mt-1 max-h-64 overflow-y-auto rounded-xl border border-sea-300 bg-white shadow-lg">
          {data.harbours.map((harbour) => (
            <li key={harbour.id}>
              <Link
                to={`/port/${harbour.slug}`}
                onClick={() => setTerm('')}
                className="flex min-h-touch items-center justify-between px-3 py-2 text-sm"
              >
                <span className="font-medium text-sea-900">{harbour.name}</span>
                <span className="text-xs text-sea-700">
                  {harbour.spot_count} place{harbour.spot_count > 1 ? 's' : ''}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
