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
    isEmbeddingMapEnabled: config?.embedding_map_enabled ?? false,
    isDbExplorerEnabled: config?.db_explorer_enabled ?? true,
  }
}
