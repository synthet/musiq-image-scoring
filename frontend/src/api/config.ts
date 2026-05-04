import { api } from './client'

export interface AppConfig {
  enable_culling: boolean
  embedding_map_enabled: boolean
}

export async function fetchConfig(): Promise<AppConfig> {
  return api.get<AppConfig>('/config')
}
