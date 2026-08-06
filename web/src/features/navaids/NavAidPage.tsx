import { Link, useParams } from 'react-router-dom'
import { NavAidSheet } from './NavAidSheet'

/** `/balise/{id}` — the SEO explainer page ("que signifie une bouée cardinale sud"). */
export default function NavAidPage(): JSX.Element {
  const { id = '' } = useParams()
  return (
    <div className="mx-auto max-w-2xl p-2">
      <nav className="px-2 py-1 text-sm">
        <Link to="/" className="underline">
          Carte
        </Link>
      </nav>
      <NavAidSheet navAidId={id.startsWith('navaid_') ? id : `navaid_${id}`} />
    </div>
  )
}
