/** @vitest-environment jsdom */
import { afterEach, describe, it, expect } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { NextChainPhaseIcons, PipelinePhaseIconsRow } from './PipelinePhaseIconsRow'
import type { RunFolderBucketPhase } from '@/types/api'

const fullBucketPhases: RunFolderBucketPhase[] = [
  { code: 'indexing', name: 'Discovery', status: 'done', done: 10, skipped: 0, failed: 0, running: 0, queued: 0, paused: 0, cancel_requested: 0, restarting: 0, total: 10, percent: 100 },
  { code: 'metadata', name: 'Inspection', status: 'done', done: 10, skipped: 0, failed: 0, running: 0, queued: 0, paused: 0, cancel_requested: 0, restarting: 0, total: 10, percent: 100 },
  { code: 'scoring', name: 'Quality Analysis', status: 'running', done: 4, skipped: 0, failed: 0, running: 1, queued: 0, paused: 0, cancel_requested: 0, restarting: 0, total: 10, percent: 42 },
  { code: 'culling', name: 'Similarity Clustering', status: 'not_started', done: 0, skipped: 0, failed: 0, running: 0, queued: 0, paused: 0, cancel_requested: 0, restarting: 0, total: 10, percent: 0 },
  { code: 'keywords', name: 'Tagging', status: 'not_started', done: 0, skipped: 0, failed: 0, running: 0, queued: 0, paused: 0, cancel_requested: 0, restarting: 0, total: 10, percent: 0 },
  { code: 'bird_species', name: 'Bird Species ID', status: 'not_started', done: 0, skipped: 0, failed: 0, running: 0, queued: 0, paused: 0, cancel_requested: 0, restarting: 0, total: 10, percent: 0 },
]

describe('PipelinePhaseIconsRow', () => {
  afterEach(() => cleanup())

  it('renders six icons for a full bucketPhases array', () => {
    const { container } = render(<PipelinePhaseIconsRow bucketPhases={fullBucketPhases} />)
    const icons = container.querySelectorAll('svg')
    expect(icons).toHaveLength(6)
  })

  it('shows em dash when phases is null', () => {
    render(<PipelinePhaseIconsRow phases={null} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('shows em dash when bucketPhases is empty', () => {
    render(<PipelinePhaseIconsRow bucketPhases={[]} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('bucket tooltip includes percent and status', () => {
    const { container } = render(<PipelinePhaseIconsRow bucketPhases={fullBucketPhases} />)
    const scoringCell = [...container.querySelectorAll('[title]')].find((el) =>
      el.getAttribute('title')?.includes('Quality Analysis: 42% (running)'),
    )
    expect(scoringCell).toBeTruthy()
  })

  it('showProgressBars renders six bar fill elements', () => {
    const { container } = render(
      <PipelinePhaseIconsRow bucketPhases={fullBucketPhases} showProgressBars />,
    )
    const fills = container.querySelectorAll('.h-full.rounded-full')
    expect(fills).toHaveLength(6)
  })

  it('running phase bar has pulse class when showProgressBars', () => {
    const { container } = render(
      <PipelinePhaseIconsRow bucketPhases={fullBucketPhases} showProgressBars />,
    )
    const pulsing = container.querySelector('.animate-pulse')
    expect(pulsing).toBeTruthy()
  })
})

describe('NextChainPhaseIcons', () => {
  afterEach(() => cleanup())

  it('renders only requested codes in pipeline order', () => {
    const { container } = render(<NextChainPhaseIcons codes={['keywords', 'scoring']} />)
    const icons = container.querySelectorAll('svg')
    expect(icons).toHaveLength(2)
    const titles = [...container.querySelectorAll('[title]')].map((el) => el.getAttribute('title'))
    expect(titles[0]).toContain('Quality Analysis')
    expect(titles[1]).toContain('Tagging')
  })

  it('renders nothing when codes is empty', () => {
    const { container } = render(<NextChainPhaseIcons codes={[]} />)
    expect(container.firstChild).toBeNull()
  })

  it('uses custom tooltip prefix', () => {
    const { container } = render(
      <NextChainPhaseIcons codes={['scoring']} tooltipPrefix="Aggregate hint" />,
    )
    const cell = container.querySelector('[title]')
    expect(cell?.getAttribute('title')).toBe('Aggregate hint: Quality Analysis')
  })
})
