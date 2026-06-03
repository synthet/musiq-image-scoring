import { describe, expect, it } from 'vitest'
import { buildPathsTableEntries, partitionScalars, tryParseJson } from './imageInspectorPartition'
import type { ImageDetail } from '@/types/api'

function keys(entries: [string, unknown][]): string[] {
  return entries.map(([k]) => k)
}

describe('partitionScalars', () => {
  const sample: ImageDetail = {
    id: 1,
    file_path: '/mnt/d/Photos/test.NEF',
    file_name: 'test.NEF',
    rating: 0,
    label: null,
    pick_status: 0,
    cull_decision: null,
    cull_policy_version: null,
    job_id: 3101,
    metadata: '{"indexing_hash_mode":"content_preview"}',
    thumbnail_path_win: 'D:\\thumbs\\a.jpg',
    stack_id: 5,
    sub_stack_id: null,
    phase_statuses: {},
    embeddings_present: { mobilenet_v2_imagenet_gap: true },
    indexing_metadata: { indexing_hash_mode: 'content_preview' },
  }

  it('routes culling, provenance, and paths correctly', () => {
    const parts = partitionScalars(sample)
    expect(keys(parts.paths)).toContain('thumbnail_path_win')
    expect(keys(parts.culling)).toEqual(expect.arrayContaining(['pick_status', 'cull_decision', 'cull_policy_version']))
    expect(keys(parts.provenance)).toEqual(['job_id'])
    expect(keys(parts.identity)).toEqual(expect.arrayContaining(['stack_id', 'sub_stack_id']))
    expect(parts.unmapped).toHaveLength(0)
  })

  it('does not place metadata in any bucket', () => {
    const parts = partitionScalars(sample)
    const all = [
      ...parts.identity,
      ...parts.paths,
      ...parts.scores,
      ...parts.user,
      ...parts.dates,
      ...parts.culling,
      ...parts.provenance,
      ...parts.unmapped,
    ].map(([k]) => k)
    expect(all).not.toContain('metadata')
  })

  it('puts unknown columns in unmapped', () => {
    const row = { ...sample, mystery_column: 'x' } as ImageDetail
    const parts = partitionScalars(row)
    expect(keys(parts.unmapped)).toContain('mystery_column')
  })

  it('routes arniqa_score to scores, not unmapped', () => {
    const row = { ...sample, arniqa_score: 0.7462 } as ImageDetail
    const parts = partitionScalars(row)
    expect(keys(parts.scores)).toContain('arniqa_score')
    expect(keys(parts.unmapped)).not.toContain('arniqa_score')
  })
})

describe('buildPathsTableEntries', () => {
  it('merges scalars, resolved_path, and file_paths in display order', () => {
    const data = {
      id: 1,
      file_path: '/mnt/d/a.NEF',
      file_name: 'a.NEF',
      resolved_path: 'D:\\Photos\\a.NEF',
      file_paths: ['D:\\Photos\\a.NEF', '/mnt/d/Photos/a.NEF'],
      thumbnail_path_win: 'D:\\thumbs\\a.jpg',
      rating: 0,
      label: null,
      pick_status: 0,
      cull_decision: null,
      cull_policy_version: null,
      job_id: null,
      phase_statuses: {},
    } as ImageDetail
    const scalars = partitionScalars(data).paths
    const rows = buildPathsTableEntries(data, scalars)
    expect(rows.map(([k]) => k)).toEqual([
      'file_path',
      'resolved_path',
      'thumbnail_path_win',
      'file_paths',
    ])
    expect(rows.find(([k]) => k === 'file_paths')?.[1]).toHaveLength(2)
  })
})

describe('tryParseJson', () => {
  it('parses JSON strings and objects', () => {
    expect(tryParseJson('{"a":1}')).toEqual({ a: 1 })
    expect(tryParseJson({ b: 2 })).toEqual({ b: 2 })
    expect(tryParseJson('not json')).toBeNull()
  })
})
