import { lazy, Suspense } from 'react'

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

import { FolderPage } from '@/pages/FolderPage'

import { StackPage } from '@/pages/StackPage'

import { BirdsPage } from '@/pages/BirdsPage'

import { KeywordsPage } from '@/pages/KeywordsPage'

import { KeywordImagesPage } from '@/pages/KeywordImagesPage'

import { ScopeSelector } from '@/components/scope/ScopeSelector'



import { useConfig } from '@/hooks/useConfig'



const GeoMapPage = lazy(() =>

  import('@/pages/GeoMapPage').then((m) => ({ default: m.GeoMapPage })),

)

const EmbeddingAtlasPage = lazy(() =>

  import('@/features/embedding-atlas/pages/EmbeddingAtlasPage').then((m) => ({

    default: m.EmbeddingAtlasPage,

  })),

)

const DbPage = lazy(() =>

  import('@/pages/DbPage').then((m) => ({ default: m.DbPage })),

)



const queryClient = new QueryClient({

  defaultOptions: {

    queries: {

      retry: 1,

      staleTime: 2000,

    },

  },

})



function RouteFallback() {

  return (

    <div className="flex flex-1 items-center justify-center p-8 text-sm text-muted-foreground">

      Loading…

    </div>

  )

}



function ProtectedAtlasRoute() {

  const { isEmbeddingMapEnabled, isLoading } = useConfig()

  if (isLoading) return null

  return isEmbeddingMapEnabled ? (

    <Suspense fallback={<RouteFallback />}>

      <EmbeddingAtlasPage />

    </Suspense>

  ) : (

    <Navigate to="/runs" replace />

  )

}



function ProtectedDbRoute() {

  const { isDbExplorerEnabled, isLoading } = useConfig()

  if (isLoading) return null

  return isDbExplorerEnabled ? (

    <Suspense fallback={<RouteFallback />}>

      <DbPage />

    </Suspense>

  ) : (

    <Navigate to="/runs" replace />

  )

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

            <Route path="/folder/:folderId" element={<FolderPage />} />

            <Route path="/stacks/:stackId" element={<StackPage />} />

            <Route path="/birds" element={<BirdsPage />} />

            <Route path="/birds/:value" element={<KeywordImagesPage kind="species" />} />

            <Route path="/keywords" element={<KeywordsPage />} />

            <Route path="/keywords/:value" element={<KeywordImagesPage kind="general" />} />

            <Route path="/embeddings" element={<ProtectedAtlasRoute />} />

            <Route path="/db" element={<ProtectedDbRoute />} />

            <Route path="/db/:tableName" element={<ProtectedDbRoute />} />

            <Route

              path="/map"

              element={(

                <Suspense fallback={<RouteFallback />}>

                  <GeoMapPage />

                </Suspense>

              )}

            />

            <Route path="/diagnostics" element={<DiagnosticsPage />} />

            <Route path="/logs" element={<LogsPage />} />

            <Route path="/settings" element={<Navigate to="/diagnostics" replace />} />

          </Route>

        </Routes>

      </BrowserRouter>

    </QueryClientProvider>

  )

}


