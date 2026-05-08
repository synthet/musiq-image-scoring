/** @vitest-environment jsdom */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ScopeSelector } from '@/components/scope/ScopeSelector'
import { useUiStore } from '@/stores/uiStore'
import { scopeApi } from '@/api/scope'

vi.mock('@tanstack/react-query', async () => {
  const actual = await vi.importActual<typeof import('@tanstack/react-query')>('@tanstack/react-query')
  return {
    ...actual,
    useMutation: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  }
})

vi.mock('@/components/status/PhaseStatusIcon', () => ({
  PhaseStatusIcon: () => <span data-testid="phase-icon" />,
}))

vi.mock('@/stores/uiStore', () => ({
  useUiStore: vi.fn(),
}))

vi.mock('@/api/scope', () => ({
  scopeApi: {
    preview: vi.fn(),
    validationRepairPreview: vi.fn(),
  },
}))

describe('ScopeSelector prerequisite prune', () => {
  const mockSetOpen = vi.fn()
  const mockSetPending = vi.fn()

  beforeEach(() => {
    vi.mocked(useUiStore).mockReturnValue({
      newRunModalOpen: true,
      setNewRunModalOpen: mockSetOpen,
      newRunInitialPath: null,
      setPendingTreeRevealPaths: mockSetPending,
    } as any)
    vi.mocked(scopeApi.preview).mockResolvedValue({
      image_count: 1,
      folder_count: 1,
      stage_statuses: {
        indexing: 'not_started',
        metadata: 'not_started',
        scoring: 'not_started',
        culling: 'not_started',
        keywords: 'not_started',
        bird_species: 'not_started',
      },
      stage_counts: {} as any,
    })
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  function renderModal() {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    return render(
      <QueryClientProvider client={qc}>
        <ScopeSelector />
      </QueryClientProvider>,
    )
  }

  it('clears an impossible keywords-only selection after preview loads', async () => {
    renderModal()
    const pathInput = screen.getByPlaceholderText(/path\/to\/folder/i)
    fireEvent.change(pathInput, { target: { value: 'D:/photos/test-scope' } })

    for (const label of ['Discovery', 'Inspection', 'Quality Analysis', 'Similarity Clustering', 'Bird Species ID']) {
      fireEvent.click(screen.getByRole('checkbox', { name: new RegExp(label, 'i') }))
    }

    fireEvent.click(screen.getByRole('button', { name: /Refresh/i }))

    await waitFor(() => {
      expect(scopeApi.preview).toHaveBeenCalled()
    })

    await waitFor(() => {
      const queueBtn = screen.getByRole('button', { name: /Queue Run/i })
      expect(queueBtn).toBeDisabled()
    })
  })
})
