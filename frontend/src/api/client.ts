const BASE = '/api'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

/** Extract FastAPI `detail` from JSON error body; otherwise return raw text. */
export function parseApiErrorDetail(text: string): string {
  const t = text.trim()
  try {
    const j = JSON.parse(t) as { detail?: string | unknown[] }
    const d = j.detail
    if (typeof d === 'string') return d
    if (Array.isArray(d)) {
      return d
        .map((x) => (typeof x === 'string' ? x : JSON.stringify(x)))
        .join('; ')
    }
  } catch {
    /* not JSON */
  }
  return t || 'Request failed'
}

async function request<T>(path: string, opts?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...opts?.headers },
    ...opts,
  })
  if (!resp.ok) {
    const text = await resp.text().catch(() => resp.statusText)
    throw new ApiError(resp.status, text)
  }
  return resp.json() as Promise<T>
}

export const api = {
  get: <T>(path: string, opts?: RequestInit) => request<T>(path, opts),
  post: <T>(path: string, body?: unknown, opts?: RequestInit) =>
    request<T>(path, {
      method: 'POST',
      body: body != null ? JSON.stringify(body) : undefined,
      ...opts,
    }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'DELETE',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
}
