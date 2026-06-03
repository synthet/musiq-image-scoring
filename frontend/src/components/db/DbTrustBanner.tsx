import { AlertTriangle } from 'lucide-react'

export function DbTrustBanner() {
  return (
    <div className="shrink-0 flex items-start gap-2 bg-[#4d3f00] border-b border-[#6b5a00] px-4 py-2 text-xs text-[#e8d48b]">
      <AlertTriangle size={14} className="shrink-0 mt-0.5" />
      <p>
        Read-only SQL explorer for trusted local use. Disable with{' '}
        <code className="text-[#f0e6b8]">database.enable_api_db_query</code> or hide the UI with{' '}
        <code className="text-[#f0e6b8]">database.db_explorer_enabled</code> in config.json.
      </p>
    </div>
  )
}
