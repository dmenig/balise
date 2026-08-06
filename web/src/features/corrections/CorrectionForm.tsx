import { useState } from 'react'
import { useCorrections } from './useCorrections'
import type { CorrectionKind, TargetType } from '../../lib/types'

const KINDS: { value: CorrectionKind; label: string; wantsPosition?: boolean }[] = [
  { value: 'wrong_position', label: 'Mauvaise position', wantsPosition: true },
  { value: 'removed', label: "N'existe plus" },
  { value: 'wrong_price', label: 'Tarif inexact' },
  { value: 'wrong_contact', label: 'Contact inexact' },
  { value: 'wrong_name', label: 'Nom inexact' },
  { value: 'other', label: 'Autre' },
]

/**
 * v1's contribution loop (docs/08): it improves *what the object is*, never *what state it is in*.
 * Works offline — the correction is queued with its timestamp and flushed on reconnect.
 */
export function CorrectionForm({
  target,
  onDone,
}: {
  target: { type: TargetType; id: string }
  onDone: () => void
}): JSX.Element {
  const { submit, busy } = useCorrections()
  const [kind, setKind] = useState<CorrectionKind>('wrong_position')
  const [note, setNote] = useState('')
  const [notice, setNotice] = useState<string | null>(null)

  const send = async () => {
    const selected = KINDS.find((item) => item.value === kind)
    const outcome = await submit(target, kind, note.trim(), {
      withPosition: selected?.wantsPosition ?? false,
    })
    setNotice(
      outcome.queued
        ? 'Signalement enregistré hors ligne — il partira à la reconnexion.'
        : 'Merci — votre signalement part en revue avant d’être appliqué au référentiel.',
    )
  }

  if (notice) {
    return (
      <div className="mt-4 rounded-xl bg-sea-50 p-3">
        <p data-testid="correction-notice" role="status" className="text-sm text-sea-900">
          {notice}
        </p>
        <button
          type="button"
          onClick={onDone}
          className="mt-2 h-touch w-full rounded-xl bg-sea-700 text-sm font-semibold text-white"
        >
          Fermer
        </button>
      </div>
    )
  }

  return (
    <form
      data-testid="correction-form"
      className="mt-4 rounded-xl border border-sea-300 p-3"
      onSubmit={(event) => {
        event.preventDefault()
        void send()
      }}
    >
      <fieldset>
        <legend className="text-sm font-semibold text-sea-900">Signaler une erreur</legend>
        <div className="mt-2 flex flex-wrap gap-2">
          {KINDS.map((item) => (
            <button
              key={item.value}
              type="button"
              aria-pressed={kind === item.value}
              data-testid={`correction-kind-${item.value}`}
              onClick={() => setKind(item.value)}
              className={`h-11 rounded-full px-3 text-xs font-medium ${
                kind === item.value
                  ? 'bg-sea-700 text-white'
                  : 'border border-sea-300 bg-white text-sea-900'
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </fieldset>
      <label className="mt-3 block text-sm">
        <span className="text-sea-700">Ce que vous avez constaté</span>
        <textarea
          value={note}
          onChange={(event) => setNote(event.target.value)}
          required
          minLength={2}
          maxLength={2000}
          rows={3}
          data-testid="correction-note"
          className="mt-1 w-full rounded-xl border border-sea-300 p-2"
          placeholder="ex. la bouée est ~40 m plus au sud"
        />
      </label>
      <p className="mt-1 text-xs text-sea-700">
        Pour une mauvaise position, votre position GPS actuelle est joignée comme proposition.
        Aucune trace de navigation n’est conservée.
      </p>
      <div className="mt-2 flex gap-2">
        <button
          type="submit"
          disabled={busy || note.trim().length < 2}
          data-testid="correction-submit"
          className="h-touch flex-1 rounded-xl bg-sea-700 text-sm font-semibold text-white disabled:opacity-60"
        >
          Envoyer
        </button>
        <button
          type="button"
          onClick={onDone}
          className="h-touch flex-1 rounded-xl border-2 border-sea-700 text-sm font-semibold text-sea-900"
        >
          Annuler
        </button>
      </div>
    </form>
  )
}
