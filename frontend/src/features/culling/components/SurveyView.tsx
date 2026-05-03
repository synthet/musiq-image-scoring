import { useQuery } from '@tanstack/react-query'
import { Loader2, Inbox } from 'lucide-react'
import { cullingApi, type CullingStack } from '../api/culling'
import { useCullingStore } from '../stores/cullingStore'
import { StackCard } from './StackCard'

interface SurveyViewProps {
  scopePath: string | null
}

export function SurveyView({ scopePath }: SurveyViewProps) {
  const activeStackId = useCullingStore((s) => s.activeStackId)
  const setActiveStackId = useCullingStore((s) => s.setActiveStackId)
  const setMode = useCullingStore((s) => s.setMode)

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['culling', 'stacks', scopePath ?? ''],
    queryFn: () => cullingApi.listStacks({ folder_path: scopePath ?? undefined }),
    enabled: scopePath != null,
  })

  if (!scopePath) {
    return (
      <EmptyState
        title="Select a folder to begin culling"
        body="Pick a scope from the dropdown above. Only folders that completed the Similarity Clustering phase will have stacks to review."
      />
    )
  }

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center text-text-muted">
        <Loader2 size={20} className="animate-spin" />
      </div>
    )
  }

  if (isError) {
    return (
      <EmptyState
        title="Could not load stacks"
        body={(error instanceof Error ? error.message : 'Unknown error.') || 'Unknown error.'}
        tone="danger"
      />
    )
  }

  const stacks: CullingStack[] = data?.stacks ?? []

  if (stacks.length === 0) {
    return (
      <EmptyState
        title="No stacks in this folder"
        body="Run the Similarity Clustering phase on this folder, then come back."
      />
    )
  }

  return (
    <div className="grid grid-cols-2 gap-3 p-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
      {stacks.map((s) => (
        <StackCard
          key={s.id}
          stack={s}
          active={s.id === activeStackId}
          onSelect={() => setActiveStackId(s.id)}
          onOpenLoupe={() => {
            setActiveStackId(s.id)
            setMode('loupe')
          }}
        />
      ))}
    </div>
  )
}

interface EmptyStateProps {
  title: string
  body: string
  tone?: 'default' | 'danger'
}

function EmptyState({ title, body, tone = 'default' }: EmptyStateProps) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
      <Inbox size={28} className={tone === 'danger' ? 'text-danger' : 'text-text-muted'} />
      <div className={tone === 'danger' ? 'text-sm text-danger' : 'text-sm text-text-secondary'}>
        {title}
      </div>
      <p className="max-w-md text-xs text-text-muted">{body}</p>
    </div>
  )
}
