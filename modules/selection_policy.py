"""
Selection Policy Module

Pure deterministic policy for pick/reject band assignment within stacks.
No I/O. Used by SelectionService for automated stack + selection workflow.

Policy constants and behavior are documented in docs/planning/refactoring/STACK_CULLING_REFACTOR_PLAN.md
"""

from math import floor

# Policy constants
DEFAULT_PICK_FRACTION = 0.33
DEFAULT_REJECT_FRACTION = 0.33
POLICY_VERSION = "1.0"

# Tie-break order for ranking (documented): score_field DESC, created_at ASC, id ASC


def band_sizes(n: int, frac: float = DEFAULT_PICK_FRACTION) -> tuple[int, int]:
    """
    Compute number of picks and rejects for a stack of size n.

    Args:
        n: Stack size
        frac: Fraction for each band (default 0.33)

    Returns:
        (picks, rejects) using floor(n * frac) for each

    Examples:
        band_sizes(1) -> (0, 0)
        band_sizes(3) -> (0, 0)
        band_sizes(4) -> (1, 1)
        band_sizes(10) -> (3, 3)
    """
    if n <= 0:
        return 0, 0
    k = floor(n * frac)
    return k, k


def classify_sorted_ids(sorted_ids: list[int], frac: float = DEFAULT_PICK_FRACTION) -> dict[int, str]:
    """
    Classify image IDs into pick/reject/neutral based on position in pre-sorted list.

    Sorted order is assumed: best first (highest score). So first k = picks, last k = rejects.

    Small-stack rules (fixed by policy):
        n=1: neutral
        n=2: 1 pick, 1 neutral
        n>=3: apply 33/33 bands

    Args:
        sorted_ids: List of image IDs sorted by score DESC, then created_at ASC, then id ASC
        frac: Fraction for pick/reject bands

    Returns:
        Dict mapping image_id -> "pick" | "reject" | "neutral"
    """
    n = len(sorted_ids)
    picks, rejects = band_sizes(n, frac)

    if n == 1:
        return {sorted_ids[0]: "neutral"}
    if n == 2:
        return {sorted_ids[0]: "pick", sorted_ids[1]: "neutral"}

    out = {}
    for i, image_id in enumerate(sorted_ids):
        if i < picks:
            out[image_id] = "pick"
        elif i >= n - rejects:
            out[image_id] = "reject"
        else:
            out[image_id] = "neutral"
    return out
