import { expect, test } from '@playwright/test'
import { acceptDisclaimer, openFilters, openMap, openSpotSheet, pickSpot } from './helpers'

/**
 * The v1 journeys from docs/13, plus the safety gate. They run against a seeded stack, so they
 * assert real data flows, not mocks.
 */

test('0 — first use blocks on the "not for navigation" notice', async ({ page }) => {
  await page.goto('/')
  const gate = page.getByRole('dialog', { name: /Avant de commencer/ })
  await expect(gate).toBeVisible()
  await expect(gate).toContainText('Ne pas utiliser pour la navigation')
  await acceptDisclaimer(page)
  // The permanent strip stays, and it is not dismissable.
  await expect(page.getByTestId('disclaimer')).toContainText('Ne pas utiliser pour la navigation')
})

test('1 — land on the map, see the spots around me, filter by kind', async ({ page }) => {
  await openMap(page)
  await expect(page.getByTestId('free-count')).toContainText('recensée')
  const before = await page.getByTestId('spot-list-item').count()

  await openFilters(page)
  await page.getByTestId('filter-kind-mooring_buoy').click()
  await expect(page.getByTestId('filter-kind-mooring_buoy')).toHaveAttribute('aria-pressed', 'true')
  await expect(async () => {
    const after = await page.getByTestId('spot-list-item').count()
    expect(after).toBeGreaterThan(0)
    expect(after).toBeLessThanOrEqual(before)
  }).toPass()
})

test('2 — open a spot sheet and read the depth at low water and the harbour contact', async ({
  page,
  request,
}) => {
  const spot = await pickSpot(request)
  await openSpotSheet(page, spot)
  const sheet = page.getByTestId('spot-sheet')
  await expect(sheet).toContainText('Profondeur (carte)')
  await expect(sheet).toContainText('Profondeur à la BM')
  await expect(sheet).toContainText('vérifiez toujours')
  // v1 answers "is it free" honestly: it says it does not know, and offers the phone.
  await expect(sheet.getByTestId('status-badge')).toHaveAttribute('data-state', 'unknown')
  await expect(sheet.getByTestId('status-badge')).toContainText('Disponibilité inconnue')
})

test('3 — filter by boat size: the spots that do not fit disappear', async ({ page }) => {
  await openMap(page)
  const before = await page.getByTestId('spot-list-item').count()
  expect(before).toBeGreaterThan(0)

  await openFilters(page)
  await page.getByTestId('filter-draft').fill('3.5')
  await page.getByTestId('filter-loa').fill('18')

  await expect(async () => {
    const after = await page.getByTestId('spot-list-item').count()
    expect(after).toBeLessThan(before)
  }).toPass({ timeout: 20_000 })

  // And the map layer is filtered with the same predicate, not just the list.
  const filtered = await page.evaluate(() => {
    const map = (window as unknown as { __baliseMap?: { getFilter: (id: string) => unknown } })
      .__baliseMap
    return map ? JSON.stringify(map.getFilter('spots')) : null
  })
  if (filtered) expect(filtered).toContain('max_draft_m')
})

test('4 — no availability anywhere in v1 (the honest-map guard)', async ({ page }) => {
  await openMap(page)
  await openFilters(page)
  const body = page.locator('body')
  await expect(body).not.toContainText('places libres')
  await expect(body).not.toContainText('Probablement libre')
  await expect(page.getByTestId('check-in')).toHaveCount(0)
  await expect(page.getByTestId('check-out')).toHaveCount(0)
})

test('5 — the harbour page renders its content with JavaScript disabled (SEO guard)', async ({
  browser,
}) => {
  const context = await browser.newContext({ javaScriptEnabled: false })
  const page = await context.newPage()
  const response = await page.goto('/port/port-de-la-trinite-sur-mer')
  expect(response?.ok()).toBeTruthy()
  const html = await page.content()
  expect(html).toContain('Balise')
  expect(html.toLowerCase()).toContain('navigation')
  await context.close()
})
