import { useMemo } from 'react'
import { Loader2 } from 'lucide-react'
import type { DbRow } from '@/api/db'

const CELL_DISPLAY_MAX = 120

function formatCell(val: unknown): { text: string; title?: string } {
  if (val === null || val === undefined) {
    return { text: 'null' }
  }
  if (Array.isArray(val)) {
    const preview = JSON.stringify(val)
    if (val.length > 8) {
      const summary = `[${val.length} values]`
      return { text: summary, title: preview.length > 200 ? `${preview.slice(0, 200)}…` : preview }
    }
    if (preview.length > CELL_DISPLAY_MAX) {
      return { text: `${preview.slice(0, CELL_DISPLAY_MAX)}…`, title: preview }
    }
    return { text: preview, title: preview.length > 40 ? preview : undefined }
  }
  if (typeof val === 'object') {
    const s = JSON.stringify(val)
    if (s.length > CELL_DISPLAY_MAX) {
      return { text: `${s.slice(0, CELL_DISPLAY_MAX)}…`, title: s }
    }
    return { text: s, title: s.length > 40 ? s : undefined }
  }
  const s = String(val)
  if (s.length > CELL_DISPLAY_MAX) {
    return { text: `${s.slice(0, CELL_DISPLAY_MAX)}…`, title: s }
  }
  return { text: s, title: s.length > 40 ? s : undefined }
}

export type DbResultGridProps = {
  rows: DbRow[]
  isLoading?: boolean
  emptyMessage?: string
}

export function DbResultGrid({ rows, isLoading, emptyMessage }: DbResultGridProps) {
  const columns = useMemo(() => {
    if (rows.length === 0) return [] as string[]
    const keys = new Set<string>()
    rows.slice(0, 10).forEach((row) => {
      Object.keys(row).forEach((k) => keys.add(k))
    })
    return Array.from(keys)
  }, [rows])

  if (!isLoading && rows.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center text-[#858585] text-sm p-8">
        {emptyMessage ?? 'No data to display.'}
      </div>
    )
  }

  return (
    <div className="flex-1 min-h-0 overflow-auto relative">
      {isLoading ? (
        <div className="absolute inset-0 flex items-center justify-center bg-[#1e1e1e]/50 backdrop-blur-sm z-10">
          <Loader2 size={24} className="animate-spin text-[#4fc1ff]" />
        </div>
      ) : null}
      <table className="w-full text-left border-collapse text-sm min-w-max">
        <thead className="sticky top-0 bg-[#252526] z-[5] shadow-sm border-b border-[#3c3c3c]">
          <tr>
            {columns.map((col) => (
              <th
                key={col}
                className="px-3 py-2 font-medium text-[#cccccc] whitespace-nowrap border-r border-[#3c3c3c] last:border-r-0"
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr
              key={rowIndex}
              className="border-b border-[#3c3c3c] hover:bg-[#2a2d2e] transition-colors"
            >
              {columns.map((col) => {
                const val = row[col]
                const isNull = val === null || val === undefined
                const isObj = typeof val === 'object' && val !== null
                const { text, title } = formatCell(val)
                return (
                  <td
                    key={col}
                    className="px-3 py-1.5 whitespace-nowrap max-w-[220px] overflow-hidden text-ellipsis border-r border-[#3c3c3c] last:border-r-0"
                    title={title}
                  >
                    {isNull ? (
                      <span className="text-[#569cd6] italic">null</span>
                    ) : isObj ? (
                      <span className="text-[#ce9178] font-mono text-xs">{text}</span>
                    ) : typeof val === 'boolean' ? (
                      <span className="text-[#569cd6]">{String(val)}</span>
                    ) : typeof val === 'number' ? (
                      <span className="text-[#b5cea8]">{text}</span>
                    ) : (
                      <span className="text-[#ce9178]">{text}</span>
                    )}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
