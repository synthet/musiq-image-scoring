import { useQuery } from '@tanstack/react-query'
import { fetchConfig, type AppConfig } from '../api/config'

export function useConfig() {
  const { data: config, isLoading, error } = useQuery<AppConfig>({
    queryKey: ['config'],
    queryFn: fetchConfig,
    staleTime: Infinity, // Config is unlikely to change during a session
  })

  return {
    config,
    isLoading,
    error,
    // Helper to check if a feature is enabled
    isCullingEnabled: config?.enable_culling ?? false,
    isEmbeddingMapEnabled: config?.embedding_map_enabled ?? false,
    isDbExplorerEnabled: config?.db_explorer_enabled ?? true,
  }
}
