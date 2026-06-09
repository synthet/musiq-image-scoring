import { describe, expect, it } from 'vitest'
import { folderPhasesToBucketPhases } from './folders'

describe('folderPhasesToBucketPhases', () => {
  it('maps API phase rows to bucket phase shape', () => {
    const rows = [
      {
        code: 'scoring',
        name: 'Scoring',
        status: 'partial',
        done_count: 5,
        failed_count: 0,
        running_count: 0,
        queued_count: 0,
        paused_count: 0,
        cancel_requested_count: 0,
        restarting_count: 0,
        skipped_count: 0,
        total_count: 10,
      },
    ]
    const mapped = folderPhasesToBucketPhases(rows)
    expect(mapped).toHaveLength(1)
    expect(mapped[0].code).toBe('scoring')
    expect(mapped[0].done).toBe(5)
    expect(mapped[0].total).toBe(10)
    expect(mapped[0].percent).toBe(50)
  })
})
