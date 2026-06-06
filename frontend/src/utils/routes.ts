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

export function parsePositiveImageId(imageId: string | number): number | null {
  const id = Math.floor(Number(imageId))
  return Number.isFinite(id) && id > 0 ? id : null
}

export function dbExplorerImageSql(imageId: string | number): string | null {
  const id = parsePositiveImageId(imageId)
  if (id == null) return null
  return `SELECT * FROM "images" WHERE id = ${id}`
}

export function dbExplorerImagePath(imageId: string | number): string {
  const id = parsePositiveImageId(imageId)
  if (id == null) return dbExplorerPath('images')
  return `${dbExplorerPath('images')}?id=${id}`
}
