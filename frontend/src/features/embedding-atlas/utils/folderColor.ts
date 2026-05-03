/**
 * Folder segment used for coloring: parent directory when possible, otherwise
 * the full normalized path (Cosmograph expects hex colors — HSL strings fail).
 */
export function parentFolderKey(filePath: string): string {
  const norm = filePath.replace(/\\/g, '/').trim();
  const i = norm.lastIndexOf('/');
  if (i > 0) return norm.slice(0, i);
  return norm || '__empty__';
}

function fnv1a32(input: string): number {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < input.length; i++) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/** Distinct hex colors (WebGL / Cosmograph-safe). Same folder → same color. */
const FOLDER_PALETTE = [
  '#22c55e',
  '#3b82f6',
  '#eab308',
  '#f97316',
  '#a855f7',
  '#ec4899',
  '#14b8a6',
  '#ef4444',
  '#84cc16',
  '#6366f1',
  '#f59e0b',
  '#8b5cf6',
  '#06b6d4',
  '#d946ef',
  '#10b981',
  '#f43f5e',
  '#0ea5e9',
  '#64748b',
] as const;

export function colorForFolderKey(folderKey: string): string {
  const key = folderKey.trim() || '__empty__';
  const idx = fnv1a32(key) % FOLDER_PALETTE.length;
  return FOLDER_PALETTE[idx]!;
}
