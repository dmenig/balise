import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { AppRoutes } from './app/routes'
import { useAppStore } from './app/store'
import './i18n'
import './styles.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      // Keep the last successful payload so a sheet stays readable when the link dies.
      gcTime: 24 * 60 * 60 * 1000,
    },
  },
})

function ThemedApp(): JSX.Element {
  const theme = useAppStore((state) => state.theme)
  if (typeof document !== 'undefined') document.documentElement.dataset.theme = theme
  return <AppRoutes />
}

const container = document.getElementById('root')
if (container) {
  createRoot(container).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <ThemedApp />
        </BrowserRouter>
      </QueryClientProvider>
    </StrictMode>,
  )
}
