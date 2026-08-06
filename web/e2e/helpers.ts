import type { APIRequestContext, BrowserContext, Page } from '@playwright/test'
import { expect } from '@playwright/test'

export const MORBIHAN_BBOX = '-3.2,47.4,-2.6,47.8'

/**
 * First use is gated by a blocking, versioned acceptance of the "not for navigation" notice
 * (docs/04 §3). Every journey that touches the map has to get past it, as a real user does.
 */
export async function acceptDisclaimer(page: Page): Promise<void> {
  const gate = page.getByRole('dialog', { name: /Avant de commencer/ })
  if (await gate.isVisible().catch(() => false)) {
    await page.getByRole('button', { name: "J'ai compris" }).click()
    await expect(gate).toBeHidden()
  }
}

export async function openMap(page: Page): Promise<void> {
  await page.goto('/')
  await acceptDisclaimer(page)
  await expect(page.getByTestId('spot-list-item').first()).toBeVisible({ timeout: 30_000 })
}

/** Filters live behind one tap so the map keeps the screen (docs/09). */
export async function openFilters(page: Page): Promise<void> {
  const toggle = page.getByTestId('toggle-filters')
  if ((await toggle.getAttribute('aria-expanded')) !== 'true') await toggle.click()
  await expect(page.getByTestId('filter-visitor')).toBeVisible()
}

export interface Spot {
  id: string
  position: [number, number]
}

/** Any mooring buoy from the seeded referential — v1 has no state to select on. */
export async function pickSpot(request: APIRequestContext): Promise<Spot> {
  const response = await request.get(`/v1/spots?bbox=${MORBIHAN_BBOX}&kind=mooring_buoy&limit=1`)
  expect(response.ok()).toBeTruthy()
  const payload = (await response.json()) as {
    features: { id: string; geometry: { coordinates: [number, number] } }[]
  }
  const feature = payload.features[0]
  expect(feature, 'the seeded fixture must contain at least one mooring buoy').toBeTruthy()
  return { id: feature!.id, position: feature!.geometry.coordinates }
}

/** Put the phone at the spot — a correction proposes the position you are standing on. */
export async function standAt(context: BrowserContext, spot: Spot): Promise<void> {
  await context.setGeolocation({ longitude: spot.position[0], latitude: spot.position[1] })
}

export async function openSpotSheet(page: Page, spot: Spot): Promise<void> {
  await page.goto(`/mouillage/${spot.id}`)
  await acceptDisclaimer(page)
  await expect(page.getByTestId('spot-sheet')).toHaveAttribute('data-spot-id', spot.id)
}
