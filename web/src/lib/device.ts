/** Anonymous device identity: one opaque token, no PII, kept in localStorage (docs/08). */
const KEY = 'balise.device_token'

export function deviceToken(): string | null {
  try {
    return localStorage.getItem(KEY)
  } catch {
    return null
  }
}

export function storeDeviceToken(token: string): void {
  try {
    localStorage.setItem(KEY, token)
  } catch {
    /* private mode: reports will be anonymous per-session, which is acceptable */
  }
}

/**
 * A device token is an opaque random string the server only ever salts and hashes, so a client
 * that first opens the app *offshore, offline* can mint its own. Without this, the very first
 * report of a trip could be queued and never flushed — the queue would have no identity to send
 * with (docs/06 T2: the contributor is created lazily, anonymously).
 */
function mintLocalToken(): string {
  const bytes = new Uint8Array(24)
  crypto.getRandomValues(bytes)
  const body = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
  return `dev_local_${body}`
}

export async function ensureDeviceToken(
  create: () => Promise<{ device_token: string }>,
): Promise<string> {
  const existing = deviceToken()
  if (existing) return existing
  try {
    const created = await create()
    storeDeviceToken(created.device_token)
    return created.device_token
  } catch {
    const local = mintLocalToken()
    storeDeviceToken(local)
    return local
  }
}

export function forgetDevice(): void {
  try {
    localStorage.removeItem(KEY)
  } catch {
    /* nothing to forget */
  }
}
