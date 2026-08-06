/**
 * v1's contribution loop: corrections to the referential (docs/08, docs/14 M2).
 *
 * It uses the same IndexedDB queue the v2 report flow will reuse — v1 needs the mechanism anyway,
 * so the seam costs nothing (docs/09 offline strategy).
 */
import { useCallback, useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { ensureDeviceToken } from '../../lib/device'
import { enqueue, flush, pendingCount } from '../../lib/queue'
import type { CorrectionKind, QueuedCorrection, TargetType } from '../../lib/types'
import { useAppStore } from '../../app/store'

const RETRY_INTERVAL_MS = 8_000

async function currentPosition(): Promise<[number, number] | undefined> {
  if (!navigator.geolocation) return undefined
  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (position) => resolve([position.coords.longitude, position.coords.latitude]),
      () => resolve(undefined),
      { timeout: 4000, maximumAge: 30_000 },
    )
  })
}

export interface CorrectionOutcome {
  queued: boolean
  error?: string
}

export function useCorrections({ autoFlush = false }: { autoFlush?: boolean } = {}) {
  const setQueued = useAppStore((state) => state.setQueued)
  const [busy, setBusy] = useState(false)

  const refreshQueue = useCallback(async () => {
    setQueued(await pendingCount())
  }, [setQueued])

  useEffect(() => {
    void refreshQueue()
  }, [refreshQueue])

  const submit = useCallback(
    async (
      target: { type: TargetType; id: string },
      kind: CorrectionKind,
      note: string,
      options: { withPosition?: boolean } = {},
    ): Promise<CorrectionOutcome> => {
      setBusy(true)
      try {
        const correction: QueuedCorrection = {
          id: `${target.id}:${kind}:${Date.now()}`,
          target,
          kind,
          note,
          created_at: new Date().toISOString(),
        }
        if (options.withPosition) {
          const position = await currentPosition()
          if (position) correction.position = position
        }
        await ensureDeviceToken(api.createDevice)
        try {
          await api.issue(correction)
          return { queued: false }
        } catch {
          // Offline or unreachable: queue it, never lose it (docs/09 rule 4).
          await enqueue(correction)
          await refreshQueue()
          return { queued: true }
        }
      } finally {
        setBusy(false)
      }
    },
    [refreshQueue],
  )

  const flushQueue = useCallback(async () => {
    await ensureDeviceToken(api.createDevice)
    const result = await flush(async (corrections) => {
      const results = await Promise.all(
        corrections.map(async (correction, index) => {
          try {
            await api.issue(correction)
            return { index, ok: true }
          } catch (error) {
            return { index, ok: false, error: (error as Error).message }
          }
        }),
      )
      return { accepted: results.filter((item) => item.ok).length, results }
    })
    await refreshQueue()
    return result
  }, [refreshQueue])

  useEffect(() => {
    // One flusher for the whole app (the banner owns it), retried on a timer because reconnecting
    // at sea is flaky and the first attempt often lands before the link is really up.
    if (!autoFlush) return
    let stopped = false
    const attempt = async () => {
      if (stopped || !navigator.onLine) return
      if ((await pendingCount()) === 0) return
      try {
        await flushQueue()
      } catch {
        /* keep the queue and try again on the next tick */
      }
    }
    const onOnline = () => void attempt()
    window.addEventListener('online', onOnline)
    const timer = window.setInterval(() => void attempt(), RETRY_INTERVAL_MS)
    void attempt()
    return () => {
      stopped = true
      window.removeEventListener('online', onOnline)
      window.clearInterval(timer)
    }
  }, [autoFlush, flushQueue])

  return { submit, flushQueue, busy }
}
