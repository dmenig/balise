import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { escales } from '../../lib/queue'

/**
 * `/mes-escales` — the spots you looked at or saved, on this device only, readable offline and
 * never uploaded (docs/04 §4). v2 adds check-ins to the same list (docs/09).
 */
export function EscalesPage(): JSX.Element {
  const [rows, setRows] = useState<{ id: string; spot_id: string; label: string; at: string }[]>([])

  useEffect(() => {
    void escales().then(setRows)
  }, [])

  return (
    <section className="mx-auto max-w-2xl p-4">
      <h1 className="text-2xl font-semibold text-sea-900">Mes escales</h1>
      <p className="mt-1 text-sm text-sea-700">
        Places consultées et enregistrées sur cet appareil uniquement. Rien n'est envoyé au serveur,
        et rien n'est conservé ailleurs que dans ce navigateur.
      </p>
      <ul className="mt-4 divide-y divide-sea-100 text-sm">
        {rows.map((row) => (
          <li key={row.id} className="py-2">
            <Link to={`/mouillage/${row.spot_id}`} className="font-medium text-sea-900 underline">
              {row.label}
            </Link>
            <span className="block text-xs text-sea-700">
              {new Date(row.at).toLocaleString('fr-FR')}
            </span>
          </li>
        ))}
        {rows.length === 0 && (
          <li className="py-2 text-sea-700">
            Aucune place enregistrée pour le moment. Ouvrez la fiche d'un mouillage : elle
            apparaîtra ici et restera lisible hors ligne.
          </li>
        )}
      </ul>
    </section>
  )
}
