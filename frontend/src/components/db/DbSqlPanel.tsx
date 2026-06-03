import { Loader2, Play } from 'lucide-react'

export type DbSqlPanelProps = {
  sql: string
  onSqlChange: (sql: string) => void
  onRun: () => void
  isRunning: boolean
  selectedTable: string | null
}

export function DbSqlPanel({ sql, onSqlChange, onRun, isRunning, selectedTable }: DbSqlPanelProps) {
  return (
    <div className="border-b border-[#3c3c3c] bg-[#1e1e1e] p-4 flex flex-col gap-2 shrink-0">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <span className="text-sm font-medium text-[#cccccc]">Custom SQL</span>
          {selectedTable ? (
            <span className="ml-2 text-xs text-[#6d6d6d] truncate">
              Table: <span className="text-[#9d9d9d] font-mono">{selectedTable}</span>
            </span>
          ) : null}
        </div>
        <button
          type="button"
          onClick={onRun}
          disabled={isRunning || !sql.trim()}
          className="flex items-center gap-1.5 bg-[#0e639c] hover:bg-[#1177bb] disabled:opacity-50 disabled:hover:bg-[#0e639c] text-white px-3 py-1.5 rounded text-xs transition-colors shrink-0"
        >
          {isRunning ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
          Run query
        </button>
      </div>
      <textarea
        value={sql}
        onChange={(e) => onSqlChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
            e.preventDefault()
            onRun()
          }
        }}
        placeholder="SELECT * FROM images LIMIT 10..."
        spellCheck={false}
        className="w-full min-h-24 max-h-48 bg-[#1e1e1e] border border-[#3c3c3c] rounded p-2 text-sm font-mono text-[#cccccc] focus:border-[#007fd4] focus:outline-none resize-y"
      />
      <p className="text-[10px] text-[#6d6d6d]">Ctrl+Enter to run. Read-only (SELECT / WITH).</p>
    </div>
  )
}
