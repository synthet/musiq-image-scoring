/** @vitest-environment jsdom */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { Sidebar } from './Sidebar'
import { MemoryRouter } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useUiStore } from '@/stores/uiStore'
import { useWsStore } from '@/stores/wsStore'

// Mock react-query
vi.mock('@tanstack/react-query', () => ({
  useQuery: vi.fn(),
  useQueryClient: vi.fn(() => ({
    invalidateQueries: vi.fn(),
  })),
}))

// Mock stores
vi.mock('@/stores/uiStore', () => ({
  useUiStore: vi.fn(),
}))

vi.mock('@/stores/wsStore', () => ({
  useWsStore: vi.fn(),
}))

// Mock API
vi.mock('@/api/scope', () => ({
  scopeApi: {
    tree: vi.fn(),
    foldersTree: vi.fn(),
  },
}))

// Mock lucide-react with simple divs
vi.mock('lucide-react', () => ({
  ChevronRight: () => <div />,
  ChevronDown: () => <div />,
  Folder: () => <div />,
  FolderOpen: () => <div />,
  Plus: () => <div />,
}))

describe('Sidebar', () => {
  const mockOpenNewRun = vi.fn()
  const mockSetSelectedScopePath = vi.fn()
  const mockSetPendingTreeRevealPaths = vi.fn()

  const sampleTree = [
    {
      path: 'd:/photos',
      name: 'Photos',
      children: [],
      phase_statuses: {}
    }
  ]

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useQuery).mockReturnValue({ data: sampleTree, isLoading: false } as any)
    vi.mocked(useUiStore).mockReturnValue({
      openNewRun: mockOpenNewRun,
      setSelectedScopePath: mockSetSelectedScopePath,
      selectedScopePath: null,
      pendingTreeRevealPaths: null,
      setPendingTreeRevealPaths: mockSetPendingTreeRevealPaths,
    })
    vi.mocked(useWsStore).mockReturnValue({ runsVersion: 0 })
  })

  afterEach(() => {
    cleanup()
  })

  it('shows "New Run" button only in Runs mode', async () => {
    // Stage 1: /runs
    const { unmount } = render(
      <MemoryRouter initialEntries={['/runs']}>
        <Sidebar />
      </MemoryRouter>
    )
    expect(screen.getByRole('button', { name: /new run/i })).toBeInTheDocument()
    unmount()
    cleanup()

    // Stage 2: /images
    render(
      <MemoryRouter initialEntries={['/images']}>
        <Sidebar />
      </MemoryRouter>
    )
    expect(screen.queryByRole('button', { name: /new run/i })).toBeNull()
  })

  it('handles double-click correctly in Runs mode', () => {
    render(
      <MemoryRouter initialEntries={['/runs']}>
        <Sidebar />
      </MemoryRouter>
    )
    
    const photosLabel = screen.getByText('Photos')
    fireEvent.doubleClick(photosLabel)
    expect(mockOpenNewRun).toHaveBeenCalledWith('d:/photos')
    
    const node = photosLabel.closest('div[title]')
    expect(node?.getAttribute('title')).toContain('Double-click to start new run')
  })

  it('handles double-click correctly in Images mode', () => {
    render(
      <MemoryRouter initialEntries={['/images']}>
        <Sidebar />
      </MemoryRouter>
    )
    
    const photosLabel = screen.getByText('Photos')
    fireEvent.doubleClick(photosLabel)
    expect(mockSetSelectedScopePath).toHaveBeenCalledWith('d:/photos')
    
    const node = photosLabel.closest('div[title]')
    expect(node?.getAttribute('title')).toContain('Double-click to view images')
  })
})
