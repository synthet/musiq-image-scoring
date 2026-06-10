import { Bird } from 'lucide-react'
import { TagCloud } from '@/components/keywords/TagCloud'
import type { KeywordCloudEntry } from '@/api/keywords'
import { speciesImagesPath } from '@/utils/routes'

function stripSpeciesPrefix(value: string): string {
  return value.replace(/^species:\s*/i, '').trim() || value
}

function speciesDisplay(entry: KeywordCloudEntry): string {
  return stripSpeciesPrefix(entry.keyword_display?.trim() || entry.keyword_norm || '')
}

export function BirdsPage() {
  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="shrink-0 border-b border-[var(--color-border-muted)] px-4 py-4 bg-[var(--color-bg-secondary)]">
        <div className="flex items-center gap-2">
          <Bird size={16} className="text-[var(--color-accent-bright)] shrink-0" />
          <h1 className="text-base font-semibold text-[var(--color-text-primary)]">Birds</h1>
        </div>
        <p className="text-xs text-[var(--color-text-muted)] mt-1">
          Species tags sized by image count. Click a species to view its images.
        </p>
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto">
        <TagCloud
          kind="species"
          hrefFor={(e) => speciesImagesPath(e.keyword_norm)}
          displayFor={speciesDisplay}
          emptyMessage="No species tags yet. Run bird-species classification to populate them."
        />
      </div>
    </div>
  )
}
