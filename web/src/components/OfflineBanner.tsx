import { useEffect } from 'react'
import { useAppStore } from '../app/store'
import { cacheAge } from '../lib/format'
import { useCorrections } from '../features/corrections/useCorrections'

/** No silent spinner over dead 4G: show the cache age and the queue depth (docs/09 rule 4). */
export function OfflineBanner(): JSX.Element | null {
  const { online, lastSyncAt, queued, setOnline } = useAppStore()
  const { flushQueue } = useCorrections({ autoFlush: true })

  useEffect(() => {
    const goOnline = () => setOnline(true)
    const goOffline = () => setOnline(false)
    window.addEventListener('online', goOnline)
    window.addEventListener('offline', goOffline)
    return () => {
      window.removeEventListener('online', goOnline)
      window.removeEventListener('offline', goOffline)
    }
  }, [setOnline])

  if (online && queued === 0) return null

  return (
    <div
      data-testid="offline-banner"
      role="status"
      className="relative z-40 flex items-center justify-between gap-2 bg-land-100 px-3 py-1 text-xs text-sea-900"
    >
      <span>
        {online ? 'En ligne' : 'Hors ligne'}
        {!online && lastSyncAt ? ` — ${cacheAge(lastSyncAt)}` : ''}
        {queued > 0 ? ` · ${queued} signalement${queued > 1 ? 's' : ''} en attente` : ''}
      </span>
      {online && queued > 0 && (
        <button
          type="button"
          data-testid="flush-queue"
          onClick={() => void flushQueue()}
          className="rounded bg-sea-700 px-2 py-1 font-semibold text-white"
        >
          Envoyer
        </button>
      )}
    </div>
  )
}
