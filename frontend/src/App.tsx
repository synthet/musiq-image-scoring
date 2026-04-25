import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Shell } from '@/components/layout/Shell'
import { RunsPage } from '@/pages/RunsPage'
import { RunDetailPage } from '@/pages/RunDetailPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { DiagnosticsPage } from '@/pages/DiagnosticsPage'
import { LogsPage } from '@/pages/LogsPage'
import { ImagesPage } from '@/pages/ImagesPage'
import { ImageInspectorPage } from '@/pages/ImageInspectorPage'
import { ScopeSelector } from '@/components/scope/ScopeSelector'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 2000,
    },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename="/ui">
        <ScopeSelector />
        <Routes>
          <Route element={<Shell />}>
            <Route index element={<Navigate to="/runs" replace />} />
            <Route path="/runs" element={<RunsPage />} />
            <Route path="/runs/:runId" element={<RunDetailPage />} />
            <Route path="/images" element={<ImagesPage />} />
            <Route path="/images/:imageId" element={<ImageInspectorPage />} />
            <Route path="/diagnostics" element={<DiagnosticsPage />} />
            <Route path="/logs" element={<LogsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
