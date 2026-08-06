import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'
import path from 'node:path'

const API_TARGET = process.env.VITE_API_PROXY ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'prompt',
      includeAssets: ['favicon.svg'],
      manifest: {
        name: 'Balise — mouillages et places de port',
        short_name: 'Balise',
        description:
          'Carte des bouées de mouillage, places visiteurs et mouillages en France. Aide à la planification, pas un instrument de navigation.',
        lang: 'fr-FR',
        theme_color: '#0b2b3c',
        background_color: '#0b2b3c',
        display: 'standalone',
        start_url: '/',
        icons: [
          { src: 'icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'icon-512.png', sizes: '512x512', type: 'image/png' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
        maximumFileSizeToCacheInBytes: 6 * 1024 * 1024,
        navigateFallback: '/index.html',
        runtimeCaching: [
          {
            // Base map + nav aid tiles: CacheFirst, 30 days, LRU-capped (docs/09).
            urlPattern: /\/v1\/tiles\/navaids\/.*/,
            handler: 'CacheFirst',
            options: {
              cacheName: 'balise-tiles-navaids',
              expiration: { maxEntries: 3000, maxAgeSeconds: 60 * 60 * 24 * 30 },
              cacheableResponse: { statuses: [0, 200, 204] },
            },
          },
          {
            urlPattern: /\/v1\/tiles\/(spots|anchorages)\/.*/,
            handler: 'CacheFirst',
            options: {
              cacheName: 'balise-tiles-spots',
              expiration: { maxEntries: 3000, maxAgeSeconds: 60 * 60 * 24 * 7 },
              cacheableResponse: { statuses: [0, 200, 204] },
            },
          },
          {
            // Sheets must stay readable offline, but a sheet carries a status: serving a cached
            // one while online would show a state the user has just changed. Network wins when
            // it answers, cache answers when it does not (docs/06 honesty rules).
            urlPattern: /\/v1\/(harbours|spots|navaids)\/.*/,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'balise-sheets',
              networkTimeoutSeconds: 4,
              expiration: { maxEntries: 500, maxAgeSeconds: 60 * 60 * 24 * 90 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          {
            // Status is never served stale from a cache: offline shows the last known age instead.
            urlPattern: /\/v1\/status.*/,
            handler: 'NetworkOnly',
          },
        ],
      },
      devOptions: { enabled: false },
    }),
  ],
  resolve: {
    alias: { '@': path.resolve(__dirname, 'src') },
  },
  server: {
    port: 5173,
    proxy: {
      '/v1': { target: API_TARGET, changeOrigin: true, ws: true },
      '/health': { target: API_TARGET, changeOrigin: true },
    },
  },
  preview: {
    port: 4173,
    proxy: {
      '/v1': { target: API_TARGET, changeOrigin: true, ws: true },
    },
  },
  build: {
    target: 'es2022',
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: (id) => (id.includes('maplibre-gl') ? 'maplibre' : undefined),
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
