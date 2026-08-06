import '@testing-library/jest-dom/vitest'

// jsdom has no IndexedDB and no geolocation; the queue and position tests provide their own doubles.
if (!('geolocation' in navigator)) {
  Object.defineProperty(navigator, 'geolocation', {
    value: {
      getCurrentPosition: (_success: PositionCallback, error?: PositionErrorCallback) =>
        error?.({ code: 1, message: 'denied' } as GeolocationPositionError),
      watchPosition: () => 0,
      clearWatch: () => undefined,
    },
    configurable: true,
  })
}
