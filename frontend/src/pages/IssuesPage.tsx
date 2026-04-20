import { useMemo, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { AlertTriangle, RefreshCcw } from 'lucide-react'
import { incidentsApi } from '@/api/incidents'
import { Button } from '@/components/ui/button'
import { imageInspectorPath } from '@/utils/inspectorLinks'
import type { ImageIncident } from '@/types/api'

const PAGE_SIZE = 50

export function IssuesPage() {
  const [page, setPage] = useState(0)
  const [folderId, setFolderId] = useState('')
  const [jobId, setJobId] = useState('')
  const [phaseCode, setPhaseCode] = useState('')
  const [kind, setKind] = useState('')

  const folderIdNum = folderId.trim() === '' ? undefined : Number(folderId)
  const jobIdNum = jobId.trim() === '' ? undefined : Number(jobId)
  const folderFilter = Number.isFinite(folderIdNum) ? folderIdNum : undefined
  const jobFilter = Number.isFinite(jobIdNum) ? jobIdNum : undefined

  const queryParams = useMemo(
    () => ({
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
      folder_id: folderFilter,
      job_id: jobFilter,
      phase_code: phaseCode.trim() || undefined,
      kind: kind.trim() || undefined,
    }),
    [page, folderFilter, jobFilter, phaseCode, kind],
  )

  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['incidents', queryParams],
    queryFn: () => incidentsApi.list(queryParams),
    placeholderData: keepPreviousData,
  })

  const items: ImageIncident[] = data?.items ?? []
  const total = data?.total ?? 0
  const maxPage = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1)

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <header className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-[#cccccc] flex items-center gap-2">
            <AlertTriangle className="text-[#cca700]" size={24} />
            Issues
          </h1>
          <p className="text-sm text-[#9d9d9d] mt-1">
            Image-scoped failures and validation records (PostgreSQL). Updates when you refresh.
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={() => refetch()} disabled={isFetching} className="gap-2">
          <RefreshCcw size={14} className={isFetching ? 'animate-spin' : ''} />
          {isFetching ? 'Refreshing…' : 'Refresh'}
        </Button>
      </header>

      <div className="flex flex-wrap gap-3 mb-4 text-xs">
        <label className="flex items-center gap-1.5 text-[#9d9d9d]">
          folder_id
          <input
            className="bg-[#3c3c3c] border border-[#555] rounded px-2 py-1 w-24 text-[#cccccc]"
            value={folderId}
            onChange={(e) => {
              setFolderId(e.target.value)
              setPage(0)
            }}
            placeholder="—"
          />
        </label>
        <label className="flex items-center gap-1.5 text-[#9d9d9d]">
          job_id
          <input
            className="bg-[#3c3c3c] border border-[#555] rounded px-2 py-1 w-24 text-[#cccccc]"
            value={jobId}
            onChange={(e) => {
              setJobId(e.target.value)
              setPage(0)
            }}
            placeholder="—"
          />
        </label>
        <label className="flex items-center gap-1.5 text-[#9d9d9d]">
          phase
          <input
            className="bg-[#3c3c3c] border border-[#555] rounded px-2 py-1 w-28 text-[#cccccc]"
            value={phaseCode}
            onChange={(e) => {
              setPhaseCode(e.target.value)
              setPage(0)
            }}
            placeholder="scoring"
          />
        </label>
        <label className="flex items-center gap-1.5 text-[#9d9d9d]">
          kind
          <input
            className="bg-[#3c3c3c] border border-[#555] rounded px-2 py-1 w-36 text-[#cccccc]"
            value={kind}
            onChange={(e) => {
              setKind(e.target.value)
              setPage(0)
            }}
            placeholder="phase_failure"
          />
        </label>
      </div>

      {isLoading && !data && (
        <div className="text-[#9d9d9d] animate-pulse py-8">Loading incidents…</div>
      )}

      {isError && (
        <div className="text-[#f44747] py-4">Failed to load incidents. Is the API reachable?</div>
      )}

      {!isLoading && data && (
        <>
          <div className="text-xs text-[#6d6d6d] mb-2">
            {total === 0 ? 'No incidents' : `Showing ${page * PAGE_SIZE + 1}–${Math.min((page + 1) * PAGE_SIZE, total)} of ${total}`}
          </div>
          <div className="rounded-lg border border-[#333333] overflow-hidden">
            <table className="w-full text-xs text-left">
              <thead className="bg-[#2a2a2a] text-[#9d9d9d]">
                <tr>
                  <th className="p-2 font-medium">Time</th>
                  <th className="p-2 font-medium">Kind</th>
                  <th className="p-2 font-medium">Phase</th>
                  <th className="p-2 font-medium">Image</th>
                  <th className="p-2 font-medium">Job</th>
                  <th className="p-2 font-medium">Message</th>
                </tr>
              </thead>
              <tbody className="text-[#cccccc] divide-y divide-[#333]">
                {items.map((row) => (
                  <tr key={row.id} className="hover:bg-[#2a2a2a]/80 align-top">
                    <td className="p-2 whitespace-nowrap text-[#9d9d9d]">
                      {row.created_at ? String(row.created_at).replace('T', ' ').slice(0, 19) : '—'}
                    </td>
                    <td className="p-2 font-mono text-[#cca700]">{row.kind}</td>
                    <td className="p-2">{row.phase_code ?? '—'}</td>
                    <td className="p-2 max-w-[200px]">
                      <Link
                        to={imageInspectorPath(row.image_id)}
                        className="text-[#4fc1ff] hover:underline"
                        title={row.file_path ?? undefined}
                      >
                        #{row.image_id}
                      </Link>
                      {row.file_path && (
                        <Link
                          to={imageInspectorPath(row.image_id)}
                          className="block text-[10px] text-[#6d6d6d] hover:text-[#4fc1ff] truncate mt-0.5"
                          title={row.file_path}
                        >
                          {row.file_path}
                        </Link>
                      )}
                    </td>
                    <td className="p-2 whitespace-nowrap">
                      {row.job_id != null ? (
                        <Link to={`/runs/${row.job_id}`} className="text-[#4fc1ff] hover:underline">
                          #{row.job_id}
                        </Link>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="p-2">
                      <div className="text-[#e0e0e0]">{row.message}</div>
                      {row.detail && Object.keys(row.detail).length > 0 && (
                        <pre className="mt-1 text-[10px] text-[#6d6d6d] whitespace-pre-wrap break-all max-h-24 overflow-auto">
                          {JSON.stringify(row.detail)}
                        </pre>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {total > PAGE_SIZE && (
            <div className="flex items-center gap-3 mt-4">
              <Button
                variant="secondary"
                size="sm"
                disabled={page <= 0}
                onClick={() => setPage((p) => Math.max(0, p - 1))}
              >
                Previous
              </Button>
              <span className="text-xs text-[#9d9d9d]">
                Page {page + 1} / {maxPage + 1}
              </span>
              <Button
                variant="secondary"
                size="sm"
                disabled={page >= maxPage}
                onClick={() => setPage((p) => Math.min(maxPage, p + 1))}
              >
                Next
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
