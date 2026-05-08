# Workflow System Diagnostics

This document outlines the diagnostic and observability instrumentation for the Vexlum Scoring backend pipeline, specifically focusing on workflow orchestration, job runners, and stall detection.

## 1. Goal / Non-goals

**Goals:**
- Provide clear visibility into the state of background workers and pipeline orchestration.
- Detect and report stalls or hanging threads during long-running batch operations.
- Expose runtime thread states and performance metrics for operators and AI agents without requiring server restarts.
- Maintain a low-dependency footprint (using standard library tools where possible).

**Non-goals:**
- Distributed tracing (e.g., OpenTelemetry) across multiple microservices (the backend is a monolith).
- Persistent metric aggregation (e.g., Prometheus/Grafana) — diagnostics are primarily for real-time inspection and log-based debugging.

## 2. Signals we need
To effectively monitor the pipeline, the following signals are instrumented:
- **Phase Timing (`phase_timer`)**: Measures the execution duration of specific logical blocks (e.g., scoring a batch, clustering a folder).
- **Worker Heartbeats**: Workers (e.g., `PipelineWorker`, `PipelineOrchestrator`) periodically update a shared registry to indicate they are alive and processing.
- **Stall Detection (`StallDetector`)**: A background watcher that compares worker heartbeats against a timeout threshold.
- **Queue Depth**: Logging the backlog of jobs/images waiting to be processed.
- **Thread Dumps**: On-demand snapshots of the Python call stack for all active threads.

## 3. Logging Contract

Diagnostics output relies heavily on structured logging to `debug.log` and `webui.log`.

- **Prefixes**: 
  - `[PERF]` for timing metrics.
  - `[STALL]` for stall detector alerts.
  - `[PIPELINE]` or `[ORCHESTRATOR]` for state transitions.
- **Required Fields**: Where applicable, logs include `job_id`, `phase_code` (using canonical DB codes: `indexing`, `metadata`, `scoring`, `culling`, `keywords`), and `thread_name`.
- **Thresholds**: 
  - `PerformanceTimer` logs a `SLOW` warning if execution exceeds `slow_threshold_ms`.
  - `StallDetector` flags a worker as stalled if no heartbeat is received within `60` seconds (configurable).

## 4. Diagnostics Surfaces

Operators and agents can access the diagnostic data through three primary surfaces:

### HTTP Endpoint
- **Route**: `GET /api/debug/thread-dump`
- **Response**: JSON containing `"success": True` and `"thread_dump": "<formatted traceback string>"`.
- **Cooldown/Rate Limiting**: Designed for manual or agent-driven debugging; rapid polling is discouraged as stack extraction has minor overhead.

### MCP Tool (Agent Access)
- **Tool**: `get_thread_dump()`
- **Signature**: Returns a dictionary with `success` and `thread_dump` keys.
- **Usage**: Used by AI agents to diagnose backend hangs without requiring terminal access.

### Operator WebUI
- **Location**: Operator Status dashboard (`/app` -> Status tab).
- **Feature**: An "Active Python threads" section lists all threads with their daemon and alive states. A **"View Thread Dump"** link directly opens the HTTP endpoint for immediate inspection.

## 5. Operational Playbook

When a pipeline job appears stuck:
1. **Check the WebUI Status Page**: Look at the "Active Python threads" list. Identify if any runner thread is missing or marked as not alive.
2. **Request a Thread Dump**: Click "View Thread Dump" (or use the MCP `get_thread_dump` tool). Look for threads blocked on I/O, database locks (`psycopg2` calls), or infinite loops.
3. **Review Logs for Stalls**: Search `debug.log` for the `[STALL]` prefix. If the `StallDetector` triggered, it will list the thread that failed to heartbeat.
4. **Review Logs for Performance**: Search for `[PERF] ... SLOW` to see if a specific phase (e.g., `tagging` or `clustering`) is simply taking exceptionally long, rather than being completely deadlocked.

## 6. Testing and Verification

- The diagnostic tools rely primarily on the Python standard library (`sys`, `traceback`, `time`, `threading`).
- Testing ignores ML/GPU dependencies (using `-m "not gpu and not db and not ml"`) ensuring diagnostic logic is robust independently of the AI models.
- **Note:** `test_culling.py` and `test_db_consistency.py` may fail during local pytest collection if the database is uninitialized, which is expected behavior for offline diagnostic checks.

## 7. Security & Privacy

- **Redaction**: Thread dumps output the raw Python stack. While local variables are not dumped by default, file paths and function names are exposed.
- **Access Control**: These tools are intended for local or authenticated administrative environments. The thread dump endpoint does not require special tokens assuming the WebUI is running in a trusted local environment (e.g., Electron host or single-user Docker).
- **Safe Logging**: The stall detector and phase timers do not log image byte content or database connection strings. File paths may be logged, which is standard for this application.
