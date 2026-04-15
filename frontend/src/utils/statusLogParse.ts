/** Parse tail lines from webui.log (text) and debug.log (JSON lines or text). */

export type StatusLogLevel = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR'

export interface ParsedStatusLine {
  level: StatusLogLevel
  message: string
  raw: string
  ts?: string
}

function normalizeLevel(s: string): StatusLogLevel {
  const u = s.toUpperCase()
  if (u === 'CRITICAL' || u === 'FATAL') return 'ERROR'
  if (u === 'WARN') return 'WARNING'
  if (u === 'DEBUG' || u === 'INFO' || u === 'WARNING' || u === 'ERROR') return u
  return 'INFO'
}

/** Standard library logging: `2026-04-14 03:46:20,487 - module - WARNING - message` */
function tryPythonLogging(line: string): ParsedStatusLine | null {
  const m = line.match(
    /^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}[.,]\d+)\s+-\s+(.+?)\s+-\s+(DEBUG|INFO|WARNING|ERROR|CRITICAL|WARN)\s+-\s+(.*)$/,
  )
  if (!m) return null
  return {
    level: normalizeLevel(m[3]),
    message: m[4],
    raw: line,
    ts: m[1].replace(',', '.'),
  }
}

/** Uvicorn / gunicorn style: `INFO:     127.0.0.1:8000 - "GET ..."` */
function tryLevelColonPrefix(line: string): ParsedStatusLine | null {
  const m = line.match(/^(DEBUG|INFO|WARNING|ERROR|CRITICAL|WARN):\s+(.*)$/)
  if (!m) return null
  return {
    level: normalizeLevel(m[1]),
    message: m[2],
    raw: line,
  }
}

/** Fallback: last ` - LEVEL - ` segment (handles odd wrappers). */
function tryMiddleLevel(line: string): ParsedStatusLine | null {
  const m = line.match(/\s-\s(DEBUG|INFO|WARNING|ERROR|CRITICAL|WARN)\s-\s(.*)$/)
  if (!m) return null
  return {
    level: normalizeLevel(m[1]),
    message: m[2],
    raw: line,
  }
}

export function parseWebuiLogLine(line: string): ParsedStatusLine {
  return (
    tryPythonLogging(line) ??
    tryLevelColonPrefix(line) ??
    tryMiddleLevel(line) ?? {
      level: 'INFO',
      message: line,
      raw: line,
    }
  )
}

function pickLevelFromObject(o: Record<string, unknown>): StatusLogLevel | undefined {
  const keys = ['level', 'severity', 'log_level', 'priority'] as const
  for (const k of keys) {
    const v = o[k]
    if (typeof v === 'string') return normalizeLevel(v)
    if (typeof v === 'number') {
      if (v >= 40) return 'ERROR'
      if (v >= 30) return 'WARNING'
      if (v >= 20) return 'INFO'
      if (v >= 10) return 'DEBUG'
    }
  }
  return undefined
}

function messageFromJsonObject(o: Record<string, unknown>): string {
  if (typeof o.message === 'string') return o.message
  if (typeof o.msg === 'string') return o.msg
  if (typeof o.text === 'string') return o.text
  try {
    return JSON.stringify(o)
  } catch {
    return String(o)
  }
}

export function parseDebugLogLine(line: string): ParsedStatusLine {
  const trimmed = line.trimEnd()
  if (!trimmed) {
    return { level: 'INFO', message: '', raw: line }
  }
  try {
    const o = JSON.parse(trimmed) as unknown
    if (o !== null && typeof o === 'object' && !Array.isArray(o)) {
      const rec = o as Record<string, unknown>
      const level = pickLevelFromObject(rec) ?? 'INFO'
      return {
        level,
        message: messageFromJsonObject(rec),
        raw: line,
      }
    }
    return {
      level: 'INFO',
      message: typeof o === 'string' ? o : JSON.stringify(o),
      raw: line,
    }
  } catch {
    return {
      level: 'INFO',
      message: trimmed,
      raw: line,
    }
  }
}

export function parseStatusLines(
  lines: string[],
  kind: 'webui' | 'debug',
): ParsedStatusLine[] {
  const fn = kind === 'webui' ? parseWebuiLogLine : parseDebugLogLine
  return lines.map((raw) => fn(raw))
}
