export function imageInspectorPath(id: number | string): string {
  return `/images/${id}`
}

export function imageInspectorAbsoluteUrl(id: number | string): string {
  const origin = typeof window !== 'undefined' ? window.location.origin : ''
  return `${origin}/ui/images/${id}`
}
