/** GET /api/status/log-tails — matches modules/ui/log_views.build_log_tails_payload.
 *  The React `/ui/logs` route requests `sources=webui` only (application log). */

export type LogTailSourceId = 'webui' | 'debug'

export interface LogTailSource {
  id: LogTailSourceId
  path: string
  exists: boolean
  lines: string[]
  total_lines: number | null
  error: string | null
}

export interface LogTailsResponse {
  ts: string
  lines_requested: number
  sources: LogTailSource[]
}
