export type PickStatus = -1 | 0 | 1

export function pickStatusOf(image: { pick_status?: number | null; rating?: number | null; label?: string | null }): PickStatus {
  if (typeof image.pick_status === 'number') {
    if (image.pick_status === 1 || image.pick_status === -1) return image.pick_status
    return 0
  }
  // Legacy fallback: derive from rating/label so picks made before the
  // pick_status column existed still light up.
  if ((image.label ?? '').toLowerCase() === 'green' || (image.rating ?? 0) >= 4) return 1
  if ((image.label ?? '').toLowerCase() === 'red' || image.rating === 1) return -1
  return 0
}

export function describePick(status: PickStatus): string {
  if (status === 1) return 'Picked'
  if (status === -1) return 'Rejected'
  return 'Unflagged'
}
