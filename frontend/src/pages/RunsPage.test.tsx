/** @vitest-environment jsdom */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useUiStore } from '@/stores/uiStore'
import { useWsStore } from '@/stores/wsStore'
import { runsApi } from '@/api/runs'
import { RunsPage } from './RunsPage'
import { DashboardPage } from './DashboardPage'

const navigate = vi.fn()

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => navigate }
})

vi.mock('@tanstack/react-query', () => ({
  useQuery: vi.fn(),
  useMutation: vi.fn(),
  useQueryClient: vi.fn(() => ({ invalidateQueries: vi.fn() })),
  keepPreviousData: undefined,
}))

vi.mock('@/stores/uiStore', () => ({ useUiStore: vi.fn() }))
vi.mock('@/stores/wsStore', () => ({ useWsStore: vi.fn() }))

vi.mock('@/api/runs', () => ({
  runsApi: {
    list: vi.fn(),
    drive: { start: vi.fn(), stop: vi.fn(), status: vi.fn() },
    folderBuckets: vi.fn(() => Promise.resolve({ items: [], total: 0, bucket_counts: {} })),
    autoDrive: vi.fn(),
  },
}))

vi.mock('@/components/runs/RunsBucketsPanel', () => ({
  RunsBucketsPanel: () => <div data-testid="runs-buckets-panel" />,
}))
vi.mock('@/components/runs/RunCard', () => ({ RunCard: () => null }))

vi.mock('lucide-react', () => ({
  Plus: () => null,
  Square: () => null,
  Zap: () => null,
  Inbox: () => null,
  ChevronLeft: () => null,
  ChevronRight: () => null,
  Bot: () => null,
  ListFilter: () => null,
  RefreshCw: () => null,
  Search: () => null,
  Play: () => null,
  CheckCircle2: () => null,
  TriangleAlert: () => null,
}))

const openNewRun = vi.fn()
let driveEnabled = false

function renderRunsPage(initial = '/runs') {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <Routes>
        <Route path="/runs" element={<RunsPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  driveEnabled = false
  navigate.mockClear()
  openNewRun.mockClear()
  ;(runsApi.drive.start as ReturnType<typeof vi.fn>).mockClear()
  ;(runsApi.drive.stop as ReturnType<typeof vi.fn>).mockClear()

  const uiState = { openNewRun, selectedScopePath: null as string | null }
  ;(useUiStore as unknown as ReturnType<typeof vi.fn>).mockImplementation(
    (sel?: (s: typeof uiState) => unknown) => (sel ? sel(uiState) : uiState),
  )
  ;(useWsStore as unknown as ReturnType<typeof vi.fn>).mockImplementation(
    (sel?: (s: { runsVersion: number }) => unknown) =>
      sel ? sel({ runsVersion: 0 }) : { runsVersion: 0 },
  )

  ;(useQuery as ReturnType<typeof vi.fn>).mockImplementation(({ queryKey }: { queryKey: unknown[] }) => {
    if (queryKey[0] === 'runs-drive-status') {
      return {
        data: {
          state: { enabled: driveEnabled },
          outstanding: { total_outstanding: 0, bucket_counts: {} },
        },
      }
    }
    if (queryKey[0] === 'runs' && queryKey[1] === 'folder-buckets') {
      return { data: { items: [], total: 0, bucket_counts: {} }, isLoading: false, isError: false, isFetching: false, refetch: vi.fn() }
    }
    return { data: [], isLoading: false }
  })

  ;(useMutation as ReturnType<typeof vi.fn>).mockImplementation(
    ({ mutationFn, onSuccess }: { mutationFn?: (v: unknown) => unknown; onSuccess?: () => void }) => ({
      mutate: (vars: unknown) => {
        mutationFn?.(vars)
        onSuccess?.()
      },
      isPending: false,
    }),
  )
})

afterEach(() => cleanup())

describe('RunsPage drive controls', () => {
  it('shows Active, Queued, and History tabs without Buckets', () => {
    renderRunsPage()
    expect(screen.getByRole('button', { name: /^active/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /^queued/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /^history/i })).toBeTruthy()
    expect(screen.queryByRole('button', { name: /^buckets$/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /^tools$/i })).toBeNull()
    expect(screen.getByRole('button', { name: /drive to complete/i })).toBeTruthy()
  })

  it('confirming the dialog starts drive and navigates to Dashboard', () => {
    renderRunsPage()
    fireEvent.click(screen.getByRole('button', { name: /drive to complete/i }))
    fireEvent.click(screen.getByRole('button', { name: /start driving/i }))

    expect(runsApi.drive.start).toHaveBeenCalledTimes(1)
    const body = (runsApi.drive.start as ReturnType<typeof vi.fn>).mock.calls[0][0]
    expect(body.target_phases).toContain('bird_species')
    expect(body.generate_captions).toBe(true)
    expect(navigate).toHaveBeenCalledWith('/dashboard')
  })

  it('renders a Stop Driving control while a drive is active', () => {
    driveEnabled = true
    renderRunsPage()
    const stopBtn = screen.getByRole('button', { name: /stop driving/i })
    fireEvent.click(stopBtn)
    expect(runsApi.drive.stop).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('button', { name: /drive to complete/i })).toBeNull()
  })
})

describe('DashboardPage', () => {
  it('renders the buckets panel', () => {
    renderRunsPage('/dashboard')
    expect(screen.getByRole('heading', { name: /^dashboard$/i })).toBeTruthy()
    expect(screen.getByTestId('runs-buckets-panel')).toBeTruthy()
  })
})
