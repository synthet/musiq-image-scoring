"""Shared route helpers for job/stage/step lifecycle control."""

from typing import Optional

from fastapi import HTTPException

from modules import db

def http_for_transition_error(exc: Exception):
    msg = str(exc)
    if "Invalid" in msg and "transition" in msg:
        raise HTTPException(status_code=409, detail=msg)
    raise exc

def control_job(job_id: int, target_status: str, reason: Optional[str] = None):
    job = db.get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        db.update_job_status(job_id, target_status, log=reason)
        return db.get_job_by_id(job_id)
    except Exception as exc:
        http_for_transition_error(exc)

def control_stage(job_id: int, phase_code: str, target_state: str, reason: Optional[str] = None):
    job = db.get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    phases = db.get_job_phases(job_id)
    if not any((p.get("phase_code") or "").strip().lower() == phase_code.strip().lower() for p in phases):
        raise HTTPException(status_code=404, detail=f"Stage not found: {phase_code}")
    try:
        rows = db.set_job_phase_state(job_id, phase_code.strip().lower(), target_state, error_message=reason)
        return rows
    except Exception as exc:
        http_for_transition_error(exc)

def control_step(image_id: int, phase_code: str, target_status: str, reason: Optional[str] = None):
    try:
        db.set_image_phase_status(image_id, phase_code.strip().lower(), target_status, error=reason)
        return db.get_image_phase_statuses(image_id)
    except Exception as exc:
        http_for_transition_error(exc)
