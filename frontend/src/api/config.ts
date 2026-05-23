import { api } from './client'

export interface ModelMembership {
  enabled?: boolean
  shadow?: boolean
}

export interface AppConfig {
  enable_culling: boolean
  embedding_map_enabled: boolean
  db_explorer_enabled: boolean
  /** scoring.models membership map: { model_name: { enabled, shadow } } */
  scoring_models?: Record<string, ModelMembership>
}

export async function fetchConfig(): Promise<AppConfig> {
  return api.get<AppConfig>('/config')
}
