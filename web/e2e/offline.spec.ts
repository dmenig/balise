import { expect, test } from '@playwright/test'
import { openMap, pickSpot, standAt } from './helpers'

/**
 * Journey 4 (docs/13), the one that decides whether this app is usable at sea:
 * download an area → go offline → still read it → queue a **correction** → reconnect → flush.
 *
 * The queue is v1's, and v2 reuses it for availability reports rather than inventing it (docs/09).
 */
test('download an area, go offline, read it, queue a correction, reconnect, flush', async ({
  page,
  context,
  request,
}) => {
  const spot = await pickSpot(request)
  await standAt(context, spot)
  await openMap(page)

  // Warm the caches for this area…
  await page.getByTestId('download-area').click()
  await expect(page.getByTestId('download-done')).toBeVisible({ timeout: 180_000 })

  // …then open a sheet while still online and let it finish loading, so its payload is cached.
  await page.getByTestId('spot-list-item').first().click()
  await expect(page.getByTestId('spot-sheet')).toContainText('Profondeur (carte)')

  await context.setOffline(true)
  await page.evaluate(() => window.dispatchEvent(new Event('offline')))
  await expect(page.getByTestId('offline-banner')).toContainText('Hors ligne')

  // The sheet stays readable offline…
  await expect(page.getByTestId('spot-sheet')).toBeVisible()
  await expect(page.getByTestId('spot-sheet')).toContainText('Profondeur (carte)')

  // …and a correction written at sea is queued instead of lost.
  await page.getByTestId('report-correction').click()
  await page.getByTestId('correction-kind-wrong_position').click()
  await page.getByTestId('correction-note').fill('la bouée est ~40 m plus au sud')
  await page.getByTestId('correction-submit').click()
  await expect(page.getByTestId('correction-notice')).toContainText('hors ligne')
  await expect(page.getByTestId('offline-banner')).toContainText('en attente')

  await context.setOffline(false)
  await page.evaluate(() => window.dispatchEvent(new Event('online')))

  // Reconnecting auto-flushes (a single owner, docs/09); the button is only a manual retry, and it
  // disappears the moment the queue drains — so try it, and do not fail if it already vanished.
  await page
    .getByTestId('flush-queue')
    .click({ timeout: 5_000 })
    .catch(() => {})
  // Once the queue drains the banner disappears entirely, so assert on the text, not the element.
  await expect(page.getByText('en attente')).toHaveCount(0, { timeout: 60_000 })
})
