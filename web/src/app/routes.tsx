import { Suspense, lazy } from 'react'
import { Route, Routes } from 'react-router-dom'
import { MapScreen } from './MapScreen'
import { HarbourPage } from '../features/harbours/HarbourPage'
import { EscalesPage } from '../features/escales/EscalesPage'
import { AboutPage, ContributePage, DataPage, TermsPage } from '../features/static/StaticPages'

const SpotPage = lazy(() => import('../features/spots/SpotPage'))
const NavAidPage = lazy(() => import('../features/navaids/NavAidPage'))

export function AppRoutes(): JSX.Element {
  return (
    <Suspense fallback={<p className="p-4">Chargement…</p>}>
      <Routes>
        <Route path="/" element={<MapScreen />} />
        <Route path="/carte" element={<MapScreen />} />
        <Route path="/port/:slug" element={<HarbourPage />} />
        <Route path="/mouillage/:id" element={<SpotPage />} />
        <Route path="/balise/:id" element={<NavAidPage />} />
        <Route path="/mes-escales" element={<EscalesPage />} />
        <Route path="/contribuer" element={<ContributePage />} />
        <Route path="/a-propos" element={<AboutPage />} />
        <Route path="/donnees" element={<DataPage />} />
        <Route path="/cgu" element={<TermsPage />} />
        <Route path="*" element={<MapScreen />} />
      </Routes>
    </Suspense>
  )
}
