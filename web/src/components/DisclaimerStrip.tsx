/**
 * Permanent, non-dismissable (docs/04 §3). It is part of the map chrome, not a toast.
 * The first-use acceptance is versioned and logged locally.
 */
import { useEffect, useState } from 'react'

export const DISCLAIMER =
  'Aide à la planification. Ne pas utiliser pour la navigation. Les cartes marines officielles à jour restent obligatoires (division 240).'

const ACCEPTED_KEY = 'balise.disclaimer.v1'

export function DisclaimerStrip(): JSX.Element {
  return (
    <p
      role="note"
      data-testid="disclaimer"
      className="w-full bg-sea-900 px-3 py-1 text-center text-[11px] font-medium leading-tight text-land-50 night:bg-night-bg night:text-night-fg"
    >
      {DISCLAIMER}
    </p>
  )
}

export function DisclaimerGate(): JSX.Element | null {
  const [accepted, setAccepted] = useState(true)

  useEffect(() => {
    try {
      setAccepted(localStorage.getItem(ACCEPTED_KEY) === 'true')
    } catch {
      setAccepted(true)
    }
  }, [])

  if (accepted) return null
  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-sea-900/80 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="gate-title"
    >
      <div className="w-full max-w-md rounded-t-2xl bg-white p-4 shadow-xl">
        <h2 id="gate-title" className="text-lg font-semibold text-sea-900">
          Avant de commencer
        </h2>
        <p className="mt-2 text-sm text-sea-700">{DISCLAIMER}</p>
        <p className="mt-2 text-sm text-sea-700">
          Les disponibilités affichées sont des signalements datés (port, communauté), jamais une
          garantie. Vérifiez toujours votre amarrage.
        </p>
        <button
          type="button"
          className="mt-4 h-touch w-full rounded-xl bg-sea-700 text-base font-semibold text-white"
          onClick={() => {
            try {
              localStorage.setItem(ACCEPTED_KEY, 'true')
            } catch {
              /* private mode: ask again next session */
            }
            setAccepted(true)
          }}
        >
          J'ai compris
        </button>
      </div>
    </div>
  )
}
