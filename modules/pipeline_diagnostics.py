"""
Pipeline Diagnostics Engine

Provides deep observability for the automated workflows:
- Thread dumping and stack trace capture
- Worker heartbeat tracking and stall detection
- Phase transition and timing telemetry
- Full pipeline state snapshotting
"""

import sys
import threading
import traceback
import time
import logging
from typing import Dict, Any, List, Optional
from contextlib import contextmanager

from modules.run_log import runner_emit

logger = logging.getLogger("pipeline_diagnostics")

# ---------------------------------------------------------------------------
# Thread Dump Service
# ---------------------------------------------------------------------------

def capture_thread_dump(include_pipeline_only: bool = False) -> Dict[str, Any]:
    """
    Captures a real-time stack trace of all running threads using sys._current_frames().
    """
    frames = sys._current_frames()
    threads_info = []
    
    # Map thread ID to thread object for metadata
    thread_map = {t.ident: t for t in threading.enumerate()}
    
    pipeline_prefixes = ("PipelineWorker", "PrepWorker", "ScoringWorker", "ResultWorker", 
                         "ScoringRunner", "IndexingRunner", "MetadataRunner", 
                         "SelectionRunner", "MaintenanceRunner", "Orchestrator", "StallDetector")
    
    for ident, frame in frames.items():
        t = thread_map.get(ident)
        name = t.name if t else f"Thread-{ident}"
        is_daemon = t.daemon if t else False
        
        is_pipeline = name.startswith(pipeline_prefixes) or "pipeline" in name.lower() or "runner" in name.lower()
        
        if include_pipeline_only and not is_pipeline:
            continue
            
        stack = traceback.extract_stack(frame)
        formatted_stack = traceback.format_list(stack)
        
        threads_info.append({
            "ident": ident,
            "name": name,
            "daemon": is_daemon,
            "is_pipeline": is_pipeline,
            "stack": formatted_stack
        })
        
    # Sort with pipeline threads first, then by name
    threads_info.sort(key=lambda x: (not x["is_pipeline"], x["name"]))
    
    return {
        "timestamp": time.time(),
        "thread_count": len(threads_info),
        "threads": threads_info
    }


# ---------------------------------------------------------------------------
# Worker Heartbeat & Stall Detection
# ---------------------------------------------------------------------------

class WorkerHeartbeat:
    """Tracks liveness of worker threads."""
    def __init__(self, worker_id: str):
        self.worker_id = worker_id
        self._last_beat = time.time()
        self._lock = threading.Lock()
        
    def beat(self, status: str = "active"):
        with self._lock:
            self._last_beat = time.time()
            self._status = status
            
    def get_info(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "worker_id": self.worker_id,
                "last_beat": self._last_beat,
                "idle_time_s": time.time() - self._last_beat,
                "status": getattr(self, "_status", "unknown")
            }


class StallDetector:
    """
    Monitors registered heartbeats and orchestrator ticks.
    Triggers automatic thread dumps if progress stops for too long.
    """
    def __init__(self, check_interval_s: float = 10.0, stall_threshold_s: float = 60.0):
        # Try to load from config if available
        try:
            from modules import config
            diag_cfg = config.get_config_section("diagnostics") or {}
            self.check_interval_s = diag_cfg.get("check_interval_s", check_interval_s)
            self.stall_threshold_s = diag_cfg.get("stall_threshold_s", stall_threshold_s)
        except Exception:
            self.check_interval_s = check_interval_s
            self.stall_threshold_s = stall_threshold_s
            
        self._heartbeats: Dict[str, WorkerHeartbeat] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread = None
        self._last_orchestrator_tick = time.time()
        
    def register_worker(self, worker_id: str) -> WorkerHeartbeat:
        with self._lock:
            hb = WorkerHeartbeat(worker_id)
            self._heartbeats[worker_id] = hb
            return hb
            
    def unregister_worker(self, worker_id: str):
        with self._lock:
            self._heartbeats.pop(worker_id, None)
            
    def tick_orchestrator(self):
        with self._lock:
            self._last_orchestrator_tick = time.time()
            
    def start(self):
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._monitor_loop, name="StallDetector", daemon=True)
            self._thread.start()
            
    def stop(self):
        with self._lock:
            self._running = False
            # We don't join to avoid blocking
            
    def _monitor_loop(self):
        logger.info(f"StallDetector started (check={self.check_interval_s}s, threshold={self.stall_threshold_s}s)")
        while self._running:
            time.sleep(self.check_interval_s)
            self._check_stalls()
            
    def _check_stalls(self):
        now = time.time()
        stalled_workers = []
        
        with self._lock:
            orch_idle = now - self._last_orchestrator_tick
            if orch_idle > self.stall_threshold_s:
                stalled_workers.append(f"Orchestrator (idle {orch_idle:.1f}s)")
                
            for wid, hb in list(self._heartbeats.items()):
                info = hb.get_info()
                if info["idle_time_s"] > self.stall_threshold_s:
                    stalled_workers.append(f"{wid} (idle {info['idle_time_s']:.1f}s, status: {info['status']})")
                    
        if stalled_workers:
            logger.warning(f"[STALL DETECTED] No progress from: {', '.join(stalled_workers)}. Triggering diagnostic thread dump.")
            try:
                dump = capture_thread_dump(include_pipeline_only=True)
                logger.warning(f"Thread dump captured {dump['thread_count']} pipeline threads.")
                # We log the stack traces of the stalled threads for immediate debugging
                for t in dump["threads"]:
                    logger.warning(f"--- Thread: {t['name']} (ident: {t['ident']}) ---")
                    for frame_line in t["stack"][-5:]: # Just the top 5 frames to avoid log spam
                        logger.warning(frame_line.strip())
            except Exception as e:
                logger.error(f"Failed to capture thread dump during stall: {e}")

# Global singleton
_stall_detector = StallDetector()

def get_stall_detector() -> StallDetector:
    return _stall_detector


# ---------------------------------------------------------------------------
# Telemetry & State
# ---------------------------------------------------------------------------

def log_phase_transition(job_id: int, from_phase: str, to_phase: str, reason: str, folder_path: Optional[str] = None):
    """Structured logging for phase transitions."""
    msg = f"Phase transition: {from_phase} -> {to_phase} (Reason: {reason})"
    if folder_path:
        msg += f" for folder: {folder_path}"
    
    # Send to standard logger at INFO
    logger.info(f"[JOB {job_id}] {msg}")
    
    # Send to DB run_log
    from modules.run_log import emit_run_log

    emit_run_log(job_id, msg, level="INFO", phase="orchestrator")


@contextmanager
def phase_timer(phase_name: str, job_id: int = None, details: str = None):
    """Context manager to time a phase and log the duration."""
    start_time = time.time()
    start_perf = time.perf_counter()
    
    detail_str = f" ({details})" if details else ""
    logger.debug(f"[PHASE START] {phase_name}{detail_str} (job={job_id})")
    
    try:
        yield
    finally:
        end_perf = time.perf_counter()
        duration_s = end_perf - start_perf
        logger.debug(f"[PHASE END] {phase_name} completed in {duration_s:.3f}s (job={job_id})")
        if job_id:
            from modules.run_log import emit_run_log

            emit_run_log(
                job_id,
                f"Timer: {phase_name} took {duration_s:.3f}s",
                level="DEBUG",
                phase="diagnostics",
            )


def capture_pipeline_snapshot(orchestrator, runners: Dict[str, Any]) -> Dict[str, Any]:
    """Collects current state of orchestrator and all runners."""
    snap = {
        "timestamp": time.time(),
        "orchestrator": {},
        "runners": {},
        "stall_detector": {
            "running": _stall_detector._running,
            "last_orchestrator_tick_ago": time.time() - _stall_detector._last_orchestrator_tick
        }
    }
    
    if orchestrator:
        snap["orchestrator"] = {
            "active": orchestrator._active,
            "current_phase": orchestrator.current_phase,
            "folder_path": orchestrator.folder_path,
            "root_job_id": orchestrator.root_job_id,
            "phase_drain_ticks": getattr(orchestrator, "_phase_drain_ticks", 0)
        }
        
    for name, runner in runners.items():
        if runner:
            try:
                is_running, log_text, status_msg, current, total, depth = runner.get_status()
                snap["runners"][name] = {
                    "running": is_running,
                    "status_message": status_msg,
                    "progress": f"{current}/{total}",
                    "pipeline_depth": depth
                }
            except Exception:
                snap["runners"][name] = {"error": "Could not get status"}
                
    return snap


def get_thread_dump() -> str:
    """Returns a nicely formatted thread dump string for diagnostics."""
    dump = capture_thread_dump()
    lines = []
    lines.append(f"Vexlum Backend Thread Dump - {time.ctime(dump['timestamp'])}")
    lines.append(f"Total threads tracked: {dump['thread_count']}")
    lines.append("=" * 70)
    
    for t in dump["threads"]:
        status = " [DAEMON]" if t["daemon"] else ""
        pipeline = " [PIPELINE]" if t["is_pipeline"] else ""
        lines.append(f"THREAD: {t['name']} (ident: {t['ident']}){status}{pipeline}")
        
        # Simple path redaction: replace user home if detected
        user_home = os.path.expanduser("~")
        
        for frame in t["stack"]:
            line = frame.strip()
            if user_home and user_home in line:
                line = line.replace(user_home, "~")
            lines.append(f"  {line}")
        lines.append("-" * 70)
        
    return "\n".join(lines)


import os # Needed for expanduser
