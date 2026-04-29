import { useCallback, useEffect, useId, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Pause, Play, RefreshCw, ScrollText } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { StatusLogFilePanel } from '@/components/ui/StatusLogFilePanel'
import type { LogTailsResponse } from '@/types/statusLogs'

const REFETCH_INTERVAL_MS = 4000

const TAIL_OPTIONS = [100, 500, 1000, 2000] as const

function useDocumentVisible() {
  const [visible, setVisible] = useState(() =>
    typeof document !== 'undefined' ? document.visibilityState === 'visible' : true,
  )
  useEffect(() => {
    const onVis = () => setVisible(document.visibilityState === 'visible')
    document.addEventListener('visibilitychange', onVis)
    return () => document.removeEventListener('visibilitychange', onVis)
  }, [])
  return visible
}

export function LogsPage() {
  const tailSelectId = useId()
  const [linesRequested, setLinesRequested] = useState<number>(500)
  const [livePaused, setLivePaused] = useState(false)
  const [manualRefreshing, setManualRefreshing] = useState(false)
  const visible = useDocumentVisible()

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['status-log-tails', 'webui', linesRequested],
    queryFn: async (): Promise<LogTailsResponse> => {
      const params = new URLSearchParams({ sources: 'webui', lines: String(linesRequested) })
      const resp = await fetch(`/api/status/log-tails?${params}`)
      if (!resp.ok) throw new Error('Failed to fetch log tails')
      return resp.json()
    },
    placeholderData: keepPreviousData,
    refetchInterval: livePaused || !visible ? false : REFETCH_INTERVAL_MS,
  })

  const handleManualRefresh = useCallback(async () => {
    setManualRefreshing(true)
    try {
      await refetch()
    } finally {
      setManualRefreshing(false)
    }
  }, [refetch])

  const webuiSource = data?.sources.find((s) => s.id === 'webui')

  const linesLabel = data
    ? `Last ${data.lines_requested.toLocaleString()} lines (tail window)`
    : ''

  if (isLoading && !data) {
    return (
      <div className="p-8 flex items-center justify-center h-full text-[#9d9d9d] animate-pulse">
        Loading logs…
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="p-8 text-[#f44747]">
        <h1 className="text-xl font-semibold mb-4 text-[#cccccc]">Logs unavailable</h1>
        <p>Could not load logs. Ensure the backend is running and /api/status/log-tails is available.</p>
        <Button variant="secondary" onClick={() => handleManualRefresh()} className="mt-4">
          Retry
        </Button>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-[1600px] mx-auto">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-[#cccccc] flex items-center gap-2">
            <ScrollText className="text-[#4fc1ff]" size={24} />
            Logs
          </h1>
          <p className="text-sm text-[#9d9d9d] mt-1 max-w-2xl">
            Application log (webui.log). Showing the last N lines from the tail; increase the tail window for more history.
            Polling pauses when this tab is in the background. Use Pause to stop live updates entirely.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <label htmlFor={tailSelectId} className="flex items-center gap-2 text-xs text-[#9d9d9d]">
            Tail window
            <select
              id={tailSelectId}
              value={linesRequested}
              onChange={(e) => setLinesRequested(Number(e.target.value))}
              className="bg-[#1e1e1e] border border-[#3c3c3c] rounded px-2 py-1 text-[#cccccc] text-xs"
            >
              {TAIL_OPTIONS.map((n) => (
                <option key={n} value={n}>
                  {n} lines
                </option>
              ))}
            </select>
          </label>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setLivePaused((p) => !p)}
            className="gap-2"
            title={livePaused ? 'Resume automatic refresh' : 'Pause automatic refresh'}
          >
            {livePaused ? <Play size={14} /> : <Pause size={14} />}
            {livePaused ? 'Resume' : 'Pause'}
          </Button>
          <span className="text-xs text-[#6d6d6d]" title="Last successful fetch timestamp">
            Updated {data.ts}
          </span>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => handleManualRefresh()}
            disabled={manualRefreshing}
            className="gap-2"
            title="Fetch latest now"
          >
            <RefreshCw size={14} className={manualRefreshing ? 'animate-spin' : ''} />
            {manualRefreshing ? 'Refreshing…' : 'Refresh'}
          </Button>
        </div>
      </header>

      <StatusLogFilePanel
        label="Application (webui.log)"
        kind="webui"
        source={webuiSource}
        syncKey={data.ts}
        linesLoadedLabel={linesLabel}
      />
    </div>
  )
}
