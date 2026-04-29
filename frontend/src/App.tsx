import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Shell } from '@/components/layout/Shell'
import { RunsPage } from '@/pages/RunsPage'
import { RunDetailPage } from '@/pages/RunDetailPage'
import { DiagnosticsPage } from '@/pages/DiagnosticsPage'
import { LogsPage } from '@/pages/LogsPage'
import { ImagesPage } from '@/pages/ImagesPage'
import { ImageInspectorPage } from '@/pages/ImageInspectorPage'
import { EmbeddingsPage } from '@/pages/EmbeddingsPage'
import { SearchPage } from '@/pages/SearchPage'
import { GeoMapPage } from '@/pages/GeoMapPage'
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
            <Route path="/embeddings" element={<EmbeddingsPage />} />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/map" element={<GeoMapPage />} />
            <Route path="/diagnostics" element={<DiagnosticsPage />} />
            <Route path="/logs" element={<LogsPage />} />
            <Route path="/settings" element={<Navigate to="/diagnostics" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
