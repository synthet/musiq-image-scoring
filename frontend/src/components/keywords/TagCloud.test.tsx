/** @vitest-environment jsdom */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { TagCloud } from './TagCloud'
import type { KeywordCloudEntry } from '@/api/keywords'

vi.mock('@tanstack/react-query', () => ({ useQuery: vi.fn() }))
vi.mock('lucide-react', () => ({ Loader2: () => null }))

const mockUseQuery = vi.mocked(useQuery)

const entries: KeywordCloudEntry[] = [
  { keyword_norm: 'bird', keyword_display: 'bird', count: 100 },
  { keyword_norm: 'rare', keyword_display: 'rare', count: 1 },
]

function renderCloud() {
  return render(
    <MemoryRouter>
      <TagCloud kind="general" hrefFor={(e) => `/keywords/${e.keyword_norm}`} />
    </MemoryRouter>
  )
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('TagCloud', () => {
  it('renders a link per keyword with the expected href', () => {
    mockUseQuery.mockReturnValue({ data: { keywords: entries }, isLoading: false, isError: false } as never)
    renderCloud()
    const bird = screen.getByText('bird').closest('a')
    const rare = screen.getByText('rare').closest('a')
    expect(bird?.getAttribute('href')).toBe('/keywords/bird')
    expect(rare?.getAttribute('href')).toBe('/keywords/rare')
  })

  it('sizes higher-count tags larger than lower-count tags', () => {
    mockUseQuery.mockReturnValue({ data: { keywords: entries }, isLoading: false, isError: false } as never)
    renderCloud()
    const birdSize = parseInt((screen.getByText('bird') as HTMLElement).style.fontSize, 10)
    const rareSize = parseInt((screen.getByText('rare') as HTMLElement).style.fontSize, 10)
    expect(birdSize).toBeGreaterThan(rareSize)
  })

  it('shows an empty message when there are no keywords', () => {
    mockUseQuery.mockReturnValue({ data: { keywords: [] }, isLoading: false, isError: false } as never)
    render(
      <MemoryRouter>
        <TagCloud kind="species" hrefFor={() => '/x'} emptyMessage="Nothing here" />
      </MemoryRouter>
    )
    expect(screen.getByText('Nothing here')).toBeTruthy()
  })
})
