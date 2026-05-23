import { api } from './client'

export type DbRow = Record<string, unknown>

export interface DbQueryRequest {
  sql: string
  params?: unknown[]
  signal?: AbortSignal
}

interface DbQueryResponse {
  data?: DbRow[]
  rows?: DbRow[]
  rowcount?: number
}

export const DB_PAGE_SIZES = [25, 50, 100, 250] as const
export type DbPageSize = (typeof DB_PAGE_SIZES)[number]

/** Default server read cap when config is unknown (matches database.api_db_query_max_rows). */
export const DEFAULT_API_DB_MAX_ROWS = 5000

function parseRows(body: DbQueryResponse): DbRow[] {
  if (Array.isArray(body.data)) return body.data
  if (Array.isArray(body.rows)) return body.rows
  return []
}

function quoteTableName(tableName: string): string {
  return `"${tableName.replace(/"/g, '""')}"`
}

export const dbApi = {
  async query(request: DbQueryRequest): Promise<DbRow[]> {
    const res = await api.post<DbQueryResponse>(
      '/db/query',
      {
        sql: request.sql,
        params: request.params ?? [],
        write: false,
      },
      { signal: request.signal },
    )
    return parseRows(res)
  },

  async fetchTables(signal?: AbortSignal): Promise<string[]> {
    const rows = await this.query({
      sql: "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name",
      signal,
    })
    return rows.map((row) => String(row.table_name ?? row.TABLE_NAME ?? '')).filter(Boolean)
  },

  async fetchTableCount(tableName: string, signal?: AbortSignal): Promise<number> {
    const q = quoteTableName(tableName)
    const rows = await this.query({
      sql: `SELECT COUNT(*) AS count FROM ${q}`,
      signal,
    })
    const raw = rows[0]?.count ?? rows[0]?.COUNT
    return Number(raw) || 0
  },

  async fetchTablePage(
    tableName: string,
    limit: number,
    offset: number,
    signal?: AbortSignal,
  ): Promise<DbRow[]> {
    const q = quoteTableName(tableName)
    const lim = Math.max(1, Math.min(250, Math.floor(limit)))
    const off = Math.max(0, Math.floor(offset))
    return this.query({
      sql: `SELECT * FROM ${q} LIMIT ${lim} OFFSET ${off}`,
      signal,
    })
  },
}
