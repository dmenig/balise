import { defineConfig, devices } from '@playwright/test'

const PORT = 4173
const BASE_URL = process.env.E2E_BASE_URL ?? `http://localhost:${PORT}`

/**
 * The five journeys that matter (docs/13). The offline one — download an area, go offline, read,
 * queue a report, reconnect, flush — is a first-class CI test, not a manual check.
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: BASE_URL,
    viewport: { width: 390, height: 844 }, // a phone on deck, not a desktop
    permissions: ['geolocation'],
    geolocation: { latitude: 47.55, longitude: -2.94 },
    locale: 'fr-FR',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'mobile-chromium', use: { ...devices['Pixel 5'] } }],
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: 'pnpm preview',
        port: PORT,
        reuseExistingServer: true,
        timeout: 120_000,
      },
})
