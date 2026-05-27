import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Shell } from '@/components/layout/Shell'
import { RunsPage } from '@/pages/RunsPage'
import { DashboardPage } from '@/pages/DashboardPage'
import { RunDetailPage } from '@/pages/RunDetailPage'
import { DiagnosticsPage } from '@/pages/DiagnosticsPage'
import { LogsPage } from '@/pages/LogsPage'
import { ImagesPage } from '@/pages/ImagesPage'
import { ImageInspectorPage } from '@/pages/ImageInspectorPage'
import { GeoMapPage } from '@/pages/GeoMapPage'
import { EmbeddingAtlasPage } from '@/features/embedding-atlas/pages/EmbeddingAtlasPage'
import { DbPage } from '@/pages/DbPage'
import { ScopeSelector } from '@/components/scope/ScopeSelector'

import { useConfig } from '@/hooks/useConfig'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 2000,
    },
  },
})

function ProtectedAtlasRoute() {
  const { isEmbeddingMapEnabled, isLoading } = useConfig()
  if (isLoading) return null
  return isEmbeddingMapEnabled ? <EmbeddingAtlasPage /> : <Navigate to="/runs" replace />
}

function ProtectedDbRoute() {
  const { isDbExplorerEnabled, isLoading } = useConfig()
  if (isLoading) return null
  return isDbExplorerEnabled ? <DbPage /> : <Navigate to="/runs" replace />
}

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
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/images" element={<ImagesPage />} />
            <Route path="/images/:imageId" element={<ImageInspectorPage />} />
            <Route path="/embeddings" element={<ProtectedAtlasRoute />} />
            <Route path="/db" element={<ProtectedDbRoute />} />
            <Route path="/db/:tableName" element={<ProtectedDbRoute />} />
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
