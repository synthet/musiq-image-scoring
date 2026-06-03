import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { DB_PAGE_SIZES, type DbPageSize } from '@/api/db'

export type DbPaginationBarProps = {
  page: number
  pageSize: DbPageSize
  onPageChange: (page: number) => void
  onPageSizeChange: (size: DbPageSize) => void
  rangeLabel: string
  canPrev: boolean
  canNext: boolean
  capHint?: string | null
}

export function DbPaginationBar({
  page,
  pageSize,
  onPageChange,
  onPageSizeChange,
  rangeLabel,
  canPrev,
  canNext,
  capHint,
}: DbPaginationBarProps) {
  return (
    <div className="shrink-0 border-t border-[#3c3c3c] bg-[#252526] px-4 py-2 flex flex-wrap items-center gap-3">
      <Button variant="secondary" size="sm" disabled={!canPrev} onClick={() => onPageChange(page - 1)}>
        <ChevronLeft size={12} />
        Prev
      </Button>
      <Button variant="secondary" size="sm" disabled={!canNext} onClick={() => onPageChange(page + 1)}>
        Next
        <ChevronRight size={12} />
      </Button>
      <span className="text-xs text-[#9d9d9d]">{rangeLabel}</span>
      {capHint ? <span className="text-xs text-[#cca700]">{capHint}</span> : null}
      <label className="ml-auto flex items-center gap-1.5 text-xs text-[#6d6d6d]">
        <span>Page size</span>
        <select
          value={pageSize}
          onChange={(e) => onPageSizeChange(Number(e.target.value) as DbPageSize)}
          className="bg-[#1e1e1e] border border-[#474747] rounded px-1.5 py-0.5 text-[#cccccc] outline-none focus:border-[#4fc1ff]"
        >
          {DB_PAGE_SIZES.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      </label>
    </div>
  )
}
