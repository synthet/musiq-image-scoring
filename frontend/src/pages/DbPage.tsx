import { useEffect, useMemo, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { AlertCircle } from 'lucide-react'
import { ApiError, parseApiErrorDetail } from '@/api/client'
import {
  dbApi,
  DEFAULT_API_DB_MAX_ROWS,
  type DbPageSize,
  type DbRow,
} from '@/api/db'
import { DbPaginationBar } from '@/components/db/DbPaginationBar'
import { DbResultGrid } from '@/components/db/DbResultGrid'
import { DbSqlPanel } from '@/components/db/DbSqlPanel'
import { DbTableSidebar } from '@/components/db/DbTableSidebar'
import { DbTrustBanner } from '@/components/db/DbTrustBanner'

type ViewMode = 'table' | 'sql'

function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return parseApiErrorDetail(err.message)
  if (err instanceof Error) return err.message
  return String(err)
}

function isAbortError(err: unknown): boolean {
  return err instanceof DOMException && err.name === 'AbortError'
}

export function DbPage() {
  const [tableListOpen, setTableListOpen] = useState(true)
  const [selectedTable, setSelectedTable] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<ViewMode>('table')
  const [customSql, setCustomSql] = useState('')
  const [sqlInput, setSqlInput] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState<DbPageSize>(50)
  const [sqlPage, setSqlPage] = useState(1)

  useEffect(() => {
    const onToggle = () => setTableListOpen((v) => !v)
    window.addEventListener('db-explorer-toggle-tables', onToggle)
    return () => window.removeEventListener('db-explorer-toggle-tables', onToggle)
  }, [])

  const {
    data: tables = [],
    isLoading: tablesLoading,
    error: tablesError,
  } = useQuery({
    queryKey: ['db', 'tables'],
    queryFn: ({ signal }) => dbApi.fetchTables(signal),
    staleTime: 60_000,
  })

  const { data: tableCount = 0 } = useQuery({
    queryKey: ['db', 'count', selectedTable],
    queryFn: ({ signal }) => dbApi.fetchTableCount(selectedTable!, signal),
    enabled: viewMode === 'table' && !!selectedTable,
    staleTime: 30_000,
  })

  useEffect(() => {
    setPage(1)
  }, [selectedTable, pageSize])

  useEffect(() => {
    setSqlPage(1)
  }, [sqlInput, pageSize])

  const tableOffset = (page - 1) * pageSize
  const tableTotalPages = Math.max(1, Math.ceil(tableCount / pageSize) || 1)

  const {
    data: tableRows = [],
    isLoading: tableRowsLoading,
    isFetching: tableRowsFetching,
    error: tableRowsError,
    isPlaceholderData: tablePlaceholder,
  } = useQuery({
    queryKey: ['db', 'table-page', selectedTable, page, pageSize],
    queryFn: ({ signal }) =>
      dbApi.fetchTablePage(selectedTable!, pageSize, tableOffset, signal),
    enabled: viewMode === 'table' && !!selectedTable,
    placeholderData: keepPreviousData,
  })

  const {
    data: sqlRows = [],
    isLoading: sqlLoading,
    isFetching: sqlFetching,
    error: sqlError,
  } = useQuery({
    queryKey: ['db', 'sql', sqlInput],
    queryFn: ({ signal }) => dbApi.query({ sql: sqlInput, signal }),
    enabled: viewMode === 'sql' && !!sqlInput.trim(),
    staleTime: 0,
  })

  const handleSelectTable = (table: string) => {
    setSelectedTable(table)
    setViewMode('table')
    setCustomSql(`SELECT * FROM "${table.replace(/"/g, '""')}" LIMIT ${pageSize}`)
  }

  const handleRunSql = () => {
    const trimmed = customSql.trim()
    if (!trimmed) return
    setSqlInput(trimmed)
    setViewMode('sql')
    setSqlPage(1)
  }

  const activeError = useMemo(() => {
    const err = tablesError ?? (viewMode === 'table' ? tableRowsError : sqlError)
    if (!err || isAbortError(err)) return null
    return errorMessage(err)
  }, [tablesError, tableRowsError, sqlError, viewMode])

  const sqlSliceStart = (sqlPage - 1) * pageSize
  const sqlSliceEnd = sqlSliceStart + pageSize
  const sqlPageRows: DbRow[] =
    viewMode === 'sql' ? sqlRows.slice(sqlSliceStart, sqlSliceEnd) : tableRows

  const sqlTotalPages = Math.max(1, Math.ceil(sqlRows.length / pageSize) || 1)
  const atServerCap = viewMode === 'sql' && sqlRows.length >= DEFAULT_API_DB_MAX_ROWS

  const paginationProps =
    viewMode === 'table'
      ? {
          page,
          pageSize,
          onPageChange: setPage,
          onPageSizeChange: (s: DbPageSize) => setPageSize(s),
          canPrev: page > 1,
          canNext: page < tableTotalPages && tableCount > page * pageSize,
          rangeLabel:
            tableCount === 0
              ? selectedTable
                ? '0 rows'
                : 'Select a table'
              : `Rows ${tableOffset + 1}–${Math.min(tableOffset + pageSize, tableCount)} of ${tableCount.toLocaleString()}`,
          capHint: null as string | null,
        }
      : {
          page: sqlPage,
          pageSize,
          onPageChange: setSqlPage,
          onPageSizeChange: (s: DbPageSize) => setPageSize(s),
          canPrev: sqlPage > 1,
          canNext: sqlPage < sqlTotalPages,
          rangeLabel:
            sqlRows.length === 0
              ? sqlInput
                ? '0 rows loaded'
                : 'Run a query to see results'
              : `Showing ${sqlSliceStart + 1}–${Math.min(sqlSliceEnd, sqlRows.length)} of ${sqlRows.length.toLocaleString()} loaded`,
          capHint: atServerCap
            ? `Server cap may apply (database.api_db_query_max_rows, default ${DEFAULT_API_DB_MAX_ROWS})`
            : null,
        }

  const gridLoading =
    viewMode === 'table'
      ? tableRowsLoading || (tableRowsFetching && !tablePlaceholder)
      : sqlLoading || sqlFetching

  const showPagination =
    viewMode === 'table' ? !!selectedTable : sqlRows.length > 0

  return (
    <div className="flex flex-col h-full min-h-0 bg-[#1e1e1e] text-[#cccccc]">
      <DbTrustBanner />

      {activeError ? (
        <div className="shrink-0 bg-[#5a1d1d] text-[#ffb3b3] px-4 py-2 text-xs flex items-center gap-2">
          <AlertCircle size={14} className="shrink-0" />
          <span className="font-mono break-all">{activeError}</span>
        </div>
      ) : null}

      <div className="flex flex-1 min-h-0">
        {tableListOpen ? (
          <DbTableSidebar
            tables={tables}
            selectedTable={selectedTable}
            onSelectTable={handleSelectTable}
            isLoading={tablesLoading}
          />
        ) : null}

        <div className="flex-1 flex flex-col min-w-0 min-h-0">
          <DbSqlPanel
            sql={customSql}
            onSqlChange={setCustomSql}
            onRun={handleRunSql}
            isRunning={viewMode === 'sql' && (sqlLoading || sqlFetching)}
            selectedTable={viewMode === 'table' ? selectedTable : null}
          />

          <DbResultGrid
            rows={sqlPageRows}
            isLoading={gridLoading}
            emptyMessage={
              viewMode === 'table'
                ? selectedTable
                  ? 'No rows in this page.'
                  : 'Select a table from the list or run a custom query.'
                : 'Run a custom SQL query (Ctrl+Enter).'
            }
          />

          {showPagination ? <DbPaginationBar {...paginationProps} /> : null}
        </div>
      </div>
    </div>
  )
}

/** Shell header PanelLeft toggles table list on /db via this event. */
export function dispatchDbExplorerToggleTables() {
  window.dispatchEvent(new CustomEvent('db-explorer-toggle-tables'))
}
