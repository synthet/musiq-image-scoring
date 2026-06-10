import { Tags } from 'lucide-react'
import { TagCloud } from '@/components/keywords/TagCloud'
import { keywordImagesPath } from '@/utils/routes'

export function KeywordsPage() {
  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="shrink-0 border-b border-[var(--color-border-muted)] px-4 py-4 bg-[var(--color-bg-secondary)]">
        <div className="flex items-center gap-2">
          <Tags size={16} className="text-[var(--color-accent-bright)] shrink-0" />
          <h1 className="text-base font-semibold text-[var(--color-text-primary)]">Keywords</h1>
        </div>
        <p className="text-xs text-[var(--color-text-muted)] mt-1">
          Keywords sized by image count. Click a keyword to view its images.
        </p>
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto">
        <TagCloud
          kind="general"
          hrefFor={(e) => keywordImagesPath(e.keyword_norm)}
          emptyMessage="No keywords yet. Run the keywords phase to populate them."
        />
      </div>
    </div>
  )
}
