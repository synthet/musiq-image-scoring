import { useEffect, useRef } from 'react'
import { useWsStore } from '@/stores/wsStore'
import { adaptBackendMessage } from '@/utils/adaptBackendMessage'
import type { WsEvent } from '@/types/api'

const WS_URL = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/updates`
const RECONNECT_DELAY_MS = 2000

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    let cancelled = false

    function connect() {
      if (cancelled) return
      const ws = new WebSocket(WS_URL)
      wsRef.current = ws

      ws.onopen = () => {
        if (!cancelled) useWsStore.getState().setConnected(true)
      }

      ws.onmessage = (ev) => {
        if (cancelled) return
        try {
          const raw = JSON.parse(ev.data as string) as Record<string, unknown>
          const { events, bumpRuns, bumpDrive } = adaptBackendMessage(raw)
          const store = useWsStore.getState()
          if (bumpRuns) store.bumpRunsVersion()
          if (bumpDrive) store.bumpDriveVersion()
          for (const event of events) dispatch(event)
        } catch {
          // ignore non-JSON messages
        }
      }

      ws.onclose = () => {
        if (cancelled) return
        useWsStore.getState().setConnected(false)
        reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS)
      }

      ws.onerror = () => {
        ws.close()
      }
    }

    function dispatch(event: WsEvent) {
      const store = useWsStore.getState()
      switch (event.type) {
        case 'run_progress':
          store.setRunProgress(event)
          break
        case 'stage_transition':
          store.setStageTransition(event)
          store.bumpRunsVersion()
          break
        case 'log_line':
          store.addLogLine(event)
          break
        case 'queue_update':
          store.setQueueUpdate(event)
          store.bumpRunsVersion()
          break
        case 'work_item_done':
          // Do not bump runsVersion — fires per item and causes infinite update loops.
          // Live progress comes from run_progress; stage_transition/queue_update handle invalidation.
          break
      }
    }

    connect()

    return () => {
      cancelled = true
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
}
