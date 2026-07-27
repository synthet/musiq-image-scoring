"""
Selection Metadata Module

Writes stack/burst IDs and pick/reject flags to XMP sidecars for the Selection workflow.
Reuses existing xmp module functions for Lightroom compatibility.
"""

import logging

from modules import xmp

logger = logging.getLogger(__name__)


def write_stack_id(image_path: str, stack_id: int) -> bool:
    """
    Write stack ID to XMP sidecar.
    Uses format "stack-{id}" for compatibility with write_burst_uuid.
    """
    if stack_id is None:
        return False
    burst_uuid = f"stack-{stack_id}"
    return xmp.write_burst_uuid(image_path, burst_uuid)


def write_pick_reject(image_path: str, decision: str) -> bool:
    """
    Write pick/reject flag to XMP sidecar using Lightroom-compatible format.
    decision: 'pick' | 'reject' | 'neutral'
    Maps to xmpDM:pick: 1 (picked), -1 (rejected), 0 (unflagged)
    """
    if decision == "pick":
        return xmp.write_pick_reject_flag(image_path, pick_status=1)
    if decision == "reject":
        return xmp.write_pick_reject_flag(image_path, pick_status=-1)
    if decision == "neutral":
        return xmp.write_pick_reject_flag(image_path, pick_status=0)
    logger.warning("Unknown decision '%s', skipping XMP write", decision)
    return False


def write_selection_metadata(image_path: str, stack_id: int | None, decision: str) -> tuple[bool, bool]:
    """
    Write both stack ID and pick/reject to sidecar.
    Returns (stack_ok, pick_reject_ok).
    """
    stack_ok = True
    if stack_id is not None:
        stack_ok = write_stack_id(image_path, stack_id)
    pick_reject_ok = write_pick_reject(image_path, decision)
    return stack_ok, pick_reject_ok
