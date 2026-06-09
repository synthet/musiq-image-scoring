import { api } from './client'

export interface StackAnalytics {
  scope: string
  stack_id?: number
  stack_name?: string | null
  best_image_id?: number | null
  member_count?: number
  generated_at?: string
  error?: string
  warnings?: string[]
  scores?: Record<string, unknown>
  exposure?: Record<string, unknown>
  labels?: Record<string, unknown>
  gps?: Record<string, unknown>
  keywords?: Record<string, unknown>
  embeddings?: Record<string, unknown>
  composite?: Record<string, unknown>
}

export const stacksApi = {
  analytics: (stackId: number) => api.get<StackAnalytics>(`/analytics/stacks/${stackId}`),
}
