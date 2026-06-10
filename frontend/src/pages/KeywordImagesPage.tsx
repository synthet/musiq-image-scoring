import { ArrowLeft, Bird, Tags } from 'lucide-react'
import { useNavigate, useParams } from 'react-router-dom'
import { ImageBrowsePanel } from '@/components/images/ImageBrowsePanel'
import { Button } from '@/components/ui/button'
import { birdsPath, keywordsPath } from '@/utils/routes'

export interface KeywordImagesPageProps {
  kind: 'species' | 'general'
}

function stripSpeciesPrefix(value: string): string {
  return value.replace(/^species:\s*/i, '').trim() || value
}

export function KeywordImagesPage({ kind }: KeywordImagesPageProps) {
  const { value: rawValue } = useParams<{ value: string }>()
  const navigate = useNavigate()
  const keyword = (rawValue ?? '').trim()

  const isSpecies = kind === 'species'
  const label = isSpecies ? stripSpeciesPrefix(keyword) : keyword
  const backTo = isSpecies ? birdsPath() : keywordsPath()
  const backLabel = isSpecies ? 'Back to birds' : 'Back to keywords'
  const Icon = isSpecies ? Bird : Tags

  if (!keyword) {
    return (
      <div className="p-6">
        <p className="text-sm text-[var(--color-danger)]">Missing keyword</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="shrink-0 border-b border-[var(--color-border-muted)] px-4 py-4 bg-[var(--color-bg-secondary)]">
        <div className="flex items-start gap-3">
          <Button variant="ghost" size="sm" onClick={() => navigate(backTo)} className="shrink-0 mt-0.5">
            <ArrowLeft size={14} />
          </Button>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <Icon size={16} className="text-[var(--color-accent-bright)] shrink-0" />
              <h1 className="text-base font-semibold text-[var(--color-text-primary)] truncate">{label}</h1>
            </div>
            <p className="text-xs text-[var(--color-text-muted)] mt-1 font-mono truncate" title={keyword}>
              {keyword}
            </p>
          </div>
          <button
            type="button"
            onClick={() => navigate(backTo)}
            className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-accent-bright)] shrink-0"
          >
            {backLabel}
          </button>
        </div>
      </div>

      <div className="flex-1 min-h-0">
        <ImageBrowsePanel
          filters={{ keyword, keyword_exact: true }}
          title={isSpecies ? 'Species images' : 'Keyword images'}
          subtitle={keyword}
          queryKeyPrefix={`keyword-${keyword}`}
          useGlobalSort={false}
          emptyMessage="No images for this keyword."
        />
      </div>
    </div>
  )
}
