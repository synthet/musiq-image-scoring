import { Plus } from 'lucide-react'
import { RunsBucketsPanel } from '@/components/runs/RunsBucketsPanel'
import { Button } from '@/components/ui/button'
import { useUiStore } from '@/stores/uiStore'

/** Folder bucket planner and Drive-to-Complete controls (formerly Runs → Buckets). */
export function DashboardPage() {
  const { openNewRun } = useUiStore()

  return (
    <div className="mx-auto w-full max-w-[min(1600px,100%)] p-6">
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-[var(--color-text-primary)]">Dashboard</h1>
          <p className="mt-1 text-xs text-[var(--color-text-secondary)]">
            Folder pipeline status, batch queueing, and background drive across the library.
          </p>
        </div>
        <Button variant="primary" size="sm" onClick={() => openNewRun()}>
          <Plus size={14} />
          New Run
        </Button>
      </div>
      <RunsBucketsPanel />
    </div>
  )
}
