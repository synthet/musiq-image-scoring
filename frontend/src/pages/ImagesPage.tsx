import { useMemo } from 'react'
import { Database } from 'lucide-react'
import { ImageBrowsePanel } from '@/components/images/ImageBrowsePanel'
import { useUiStore } from '@/stores/uiStore'

export function ImagesPage() {
  const selectedScopePath = useUiStore((s) => s.selectedScopePath)

  const scopeLabel = useMemo(() => {
    if (!selectedScopePath) return 'All indexed images'
    return selectedScopePath
  }, [selectedScopePath])

  return (
    <ImageBrowsePanel
      filters={{ folder_path: selectedScopePath ?? undefined }}
      title="Images"
      titleLeading={<Database size={16} className="text-[var(--color-accent-bright)]" />}
      subtitle={`Scope: ${scopeLabel}`}
    />
  )
}
