/**
 * Offline contribution queue (docs/09).
 *
 * v1 queues *corrections* to the referential; v2 reuses the same store for availability reports, so
 * the mechanism is built once. Timestamps are never rewritten at flush time — an honest "il y a 3 h"
 * beats a wrong "à l'instant".
 */
import { type IDBPDatabase, openDB } from 'idb'
import type { QueuedCorrection } from './types'

const DB_NAME = 'balise'
const STORE = 'contribution-queue'
const HISTORY = 'escales'

interface Schema {
  'contribution-queue': { key: string; value: QueuedCorrection }
  escales: { key: string; value: { id: string; spot_id: string; label: string; at: string } }
}

let handle: Promise<IDBPDatabase<Schema>> | null = null

function db(): Promise<IDBPDatabase<Schema>> {
  handle ??= openDB<Schema>(DB_NAME, 1, {
    upgrade(database) {
      if (!database.objectStoreNames.contains(STORE)) database.createObjectStore(STORE)
      if (!database.objectStoreNames.contains(HISTORY)) database.createObjectStore(HISTORY)
    },
  })
  return handle
}

export async function enqueue(report: QueuedCorrection): Promise<void> {
  const database = await db()
  await database.put(STORE, report, report.id)
}

export async function pending(): Promise<QueuedCorrection[]> {
  const database = await db()
  return database.getAll(STORE)
}

export async function pendingCount(): Promise<number> {
  const database = await db()
  return database.count(STORE)
}

export async function drop(ids: string[]): Promise<void> {
  const database = await db()
  const transaction = database.transaction(STORE, 'readwrite')
  await Promise.all(ids.map((id) => transaction.store.delete(id)))
  await transaction.done
}

export interface FlushResult {
  sent: number
  kept: number
}

/** Flush the queue. Items the server rejects for a *permanent* reason are dropped, not retried. */
export async function flush(
  send: (reports: QueuedCorrection[]) => Promise<{
    accepted: number
    results: { index: number; ok: boolean; error?: string }[]
  }>,
): Promise<FlushResult> {
  const queued = await pending()
  if (queued.length === 0) return { sent: 0, kept: 0 }
  const batch = queued.slice(0, 100)
  const response = await send(batch)
  const settled = response.results
    .filter((result) => result.ok || isPermanent(result.error))
    .map((result) => batch[result.index]?.id)
    .filter((id): id is string => Boolean(id))
  await drop(settled)
  return { sent: response.accepted, kept: await pendingCount() }
}

function isPermanent(error?: string): boolean {
  if (!error) return false
  return /inconnu|invalide|suspendu/i.test(error)
}

export async function rememberEscale(spot_id: string, label: string): Promise<void> {
  const database = await db()
  const id = `${spot_id}:${Date.now()}`
  await database.put(HISTORY, { id, spot_id, label, at: new Date().toISOString() }, id)
}

export async function escales(): Promise<
  { id: string; spot_id: string; label: string; at: string }[]
> {
  const database = await db()
  const rows = await database.getAll(HISTORY)
  return rows.sort((left, right) => right.at.localeCompare(left.at))
}
