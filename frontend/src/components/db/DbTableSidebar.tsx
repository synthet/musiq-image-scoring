import { clsx } from 'clsx'
import { NavLink } from 'react-router-dom'
import { Database, Table as TableIcon } from 'lucide-react'
import { dbExplorerPath } from '@/utils/routes'

export type DbTableSidebarProps = {
  tables: string[]
  selectedTable: string | null
  isLoading?: boolean
}

export function DbTableSidebar({
  tables,
  selectedTable,
  isLoading,
}: DbTableSidebarProps) {
  return (
    <div className="w-64 border-r border-[#3c3c3c] flex flex-col bg-[#252526] shrink-0 min-h-0">
      <div className="p-3 border-b border-[#3c3c3c] flex items-center gap-2">
        <Database size={16} className="text-[#4fc1ff]" />
        <span className="font-semibold text-sm text-[#cccccc]">Tables</span>
        {isLoading ? <span className="text-xs text-[#6d6d6d] ml-auto">…</span> : null}
      </div>
      <div className="flex-1 overflow-y-auto py-2 min-h-0">
        {tables.map((table) => (
          <NavLink
            key={table}
            to={dbExplorerPath(table)}
            className={({ isActive }) =>
              clsx(
                'w-full flex items-center gap-2 px-4 py-1.5 text-sm transition-colors text-left',
                isActive || selectedTable === table
                  ? 'bg-[#37373d] text-white'
                  : 'hover:bg-[#2a2d2e] text-[#cccccc]',
              )
            }
          >
            <TableIcon size={14} className="text-[#858585] shrink-0" />
            <span className="truncate">{table}</span>
          </NavLink>
        ))}
        {!isLoading && tables.length === 0 && (
          <div className="px-4 py-2 text-xs text-[#858585]">No tables found</div>
        )}
      </div>
    </div>
  )
}
