import { Link, useParams } from 'react-router-dom'
import { SpotSheet } from './SpotSheet'

/** `/mouillage/{id}` — a shareable, deep-linkable spot sheet. */
export default function SpotPage(): JSX.Element {
  const { id = '' } = useParams()
  return (
    <div className="mx-auto max-w-2xl p-2">
      <nav className="px-2 py-1 text-sm">
        <Link to="/" className="underline">
          Carte
        </Link>
      </nav>
      <SpotSheet spotId={id.startsWith('spot_') ? id : `spot_${id}`} />
    </div>
  )
}
