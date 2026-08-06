import type { Config } from 'tailwindcss'

/**
 * Marine palette. Two themes that both matter at sea: a high-contrast daylight theme (glare,
 * sunglasses) and a red night theme that never emits white light (docs/09 UX rule 3).
 */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: ['class', '[data-theme="night"]'],
  theme: {
    extend: {
      colors: {
        sea: {
          50: '#f2f8fb',
          100: '#dceaf2',
          300: '#8fbcd4',
          500: '#3d7f9e',
          700: '#1d4d64',
          900: '#0b2b3c',
        },
        land: { 50: '#faf7f0', 100: '#f0e9db', 300: '#d9cbaf' },
        free: { DEFAULT: '#1F9D55', soft: '#7BC08F' },
        occupied: '#6B7280',
        unknown: '#9CA3AF',
        night: { bg: '#140000', fg: '#ff6b6b', dim: '#8c2f2f' },
      },
      spacing: {
        touch: '3.5rem', // 56 px minimum touch target — wet fingers, gloves, a moving boat
      },
      fontFamily: {
        sans: ['system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
    },
  },
  plugins: [],
} satisfies Config
