import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { QueuedCorrection } from './types'

/** In-memory stand-in for idb, matching the production interface (docs/13). */
const stores = new Map<string, Map<string, unknown>>()

vi.mock('idb', () => ({
  openDB: async () => ({
    objectStoreNames: { contains: () => true },
    put: async (store: string, value: unknown, key: string) => {
      stores.get(store)?.set(key, value)
    },
    getAll: async (store: string) => [...(stores.get(store)?.values() ?? [])],
    count: async (store: string) => stores.get(store)?.size ?? 0,
    transaction: (store: string) => ({
      store: { delete: async (key: string) => void stores.get(store)?.delete(key) },
      done: Promise.resolve(),
    }),
  }),
}))

const { drop, enqueue, flush, pending, pendingCount } = await import('./queue')

function correction(id: string): QueuedCorrection {
  return {
    id,
    target: { type: 'spot', id: 'spot_1' },
    kind: 'wrong_position',
    note: 'la bouée est ~40 m plus au sud',
    created_at: '2026-08-06T10:00:00.000Z',
  }
}

describe('offline contribution queue (docs/09)', () => {
  beforeEach(() => {
    stores.set('contribution-queue', new Map())
    stores.set('escales', new Map())
  })

  it('keeps the correction verbatim through a queue round trip', async () => {
    await enqueue(correction('a'))
    expect(await pending()).toEqual([correction('a')])
  })

  it('drops accepted items and keeps the ones worth retrying', async () => {
    await enqueue(correction('a'))
    await enqueue(correction('b'))
    const result = await flush(async () => ({
      accepted: 1,
      results: [
        { index: 0, ok: true },
        { index: 1, ok: false, error: 'connexion perdue' },
      ],
    }))
    expect(result).toEqual({ sent: 1, kept: 1 })
    expect((await pending()).map((item) => item.id)).toEqual(['b'])
  })

  it('drops items the server will never accept, so the queue cannot wedge', async () => {
    await enqueue(correction('a'))
    const result = await flush(async () => ({
      accepted: 0,
      results: [{ index: 0, ok: false, error: 'Objet inconnu' }],
    }))
    expect(result).toEqual({ sent: 0, kept: 0 })
    expect(await pendingCount()).toBe(0)
  })

  it('is a no-op when nothing is queued', async () => {
    const send = vi.fn()
    expect(await flush(send)).toEqual({ sent: 0, kept: 0 })
    expect(send).not.toHaveBeenCalled()
  })

  it('can drop explicitly', async () => {
    await enqueue(correction('a'))
    await drop(['a'])
    expect(await pendingCount()).toBe(0)
  })
})
