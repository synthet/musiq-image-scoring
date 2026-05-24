export function imageInspectorPath(id: string | number): string {
  return `/images/${id}`
}

export function dbExplorerPath(tableName?: string | null): string {
  if (!tableName) return '/db'
  return `/db/${encodeURIComponent(tableName)}`
}

export function embeddingsPath(): string {
  return `/embeddings`
}

export function embeddingsPathFor(imageId: string | number): string {
  return `/embeddings?focus=${encodeURIComponent(String(imageId))}`
}
