# Fix Plan — Runs/DB/Logs audit (2026-04-22)

Companion to [RCA_runs_audit_2026-04-22.md](RCA_runs_audit_2026-04-22.md). Each entry below is a self-contained, minimal-diff change with a concrete patch point and a verification step. Ordered by ROI: the first fix alone drains the current heal backlog.

---

## FIX-1 — Align "fully scored" with scoring completeness  [HIGH, unblocks queue]

**Targets HIGH-1 (heal loop) + MED-8 (folder flag desync).**

### Change A — folder predicate matches image predicate

File: [modules/db_legacy.py:3855](modules/db_legacy.py#L3855) `check_and_update_folder_status`.

Replace the narrow `score_general > 0` column probe with the same completeness fragment the healer uses:

```python
# Before: SELECT file_name, score_general FROM images WHERE folder_id = ?
# After:
incomplete_sql = _incomplete_images_where_sql()  # no alias needed
rows = list(get_connector().query(
    f"SELECT file_name, CASE WHEN {incomplete_sql} THEN 0 ELSE 1 END AS is_complete "
    f"FROM images WHERE folder_id = ?",
    (folder_id,)
))
scored_files = {row['file_name'] for row in rows if row['is_complete']}
```

Effect: folders only flip to `is_fully_scored=1` when every image passes the same check the healer runs against. The heal-vs-engine disagreement can't happen anymore.

### Change B — reset folder flag after a no-op heal

File: [modules/engine.py:101-108](modules/engine.py#L101-L108).

When `skip_existing` triggers the skip, do a cheap recheck first:

```python
if self.skip_existing:
    try:
        if db.is_folder_scored(root):
            # One-time validation: does the flag still hold?
            if not db.check_and_update_folder_status(root):
                # Flag was stale; don't skip — fall through to scan.
                pass
            else:
                self.log(f"Skipping fully scored folder: {root}")
                continue
    except Exception as e:
        self.log(f"Error checking folder status for {root}: {e}", "WARNING")
```

This makes the skip self-healing even if Change A misses an edge case.

### Verification
- Delete-and-recheck the seven looping folders:
  ```sql
  UPDATE folders SET is_fully_scored = 0
   WHERE path IN (
     '/mnt/d/Photos/Z8/105mm/2026/2026-03-12',
     '/mnt/d/Photos/Z8/105mm/2026/2026-03-19',
     '/mnt/d/Photos/Z8/180-600mm/2026/2026-03-14',
     '/mnt/d/Photos/Z8/180-600mm/2026/2026-03-22',
     '/mnt/d/Photos/Z8/180-600mm/2026/2026-03-28',
     '/mnt/d/Photos/Z8/180-600mm/2026/2026-04-02',
     '/mnt/d/Photos/Z6ii/28-400mm/2026/2026-03-15'
   );
  ```
- Re-run scoring on one of them with `run_mode=process_unprocessed_or_empty`. Expect `images_processed > 0` (it'll fill `rating`/`label`/missing model scores) then the flag flips back to 1.
- Let healer run one cycle. Expect `get_error_summary.failed_jobs` unchanged and no new no-op completions on the same scope.
- Add a unit test that seeds an image with `score_general=0.8, rating=NULL` and asserts `check_and_update_folder_status` returns `False` (currently it would return True).

---

## FIX-2 — Pre-enqueue folder-existence check  [MED-4]

File: [modules/workflow_healing.py:152](modules/workflow_healing.py#L152) `_enqueue_heal_run`.

```python
import os

def _enqueue_heal_run(folder_path, phase_code, run_mode="validate_and_repair"):
    if not os.path.isdir(folder_path):
        logger.info("Heal skip (missing on disk): %s", folder_path)
        return None, None  # caller already tolerates exceptions; adapt
    ...
```

And in the scheduling loop at [workflow_healing.py:117-126](modules/workflow_healing.py#L117-L126):

```python
for folder in to_schedule:
    try:
        result = _enqueue_heal_run(folder["folder_path"], phase_code, run_mode=run_mode)
        if result is None or result[0] is None:
            continue  # missing on disk; logged inside
        job_id, pos = result
        scheduled_detail.append({...})
    except Exception:
        logger.exception(...)
```

### Companion — schedule `pruneMissing` daily
The MCP tool `pruneMissing` exists and ran once. Add it to the maintenance cron (or wherever `schedule_folder_quality_runs` lives) at a low frequency (daily). Out-of-scope for this ticket if the cron harness isn't in this repo — flag for follow-up.

### Verification
- `UPDATE folders SET path = '/tmp/does_not_exist' WHERE id = <some_id>;` (or temporarily rename a folder on disk).
- Trigger a heal cycle. Expect no "Path not found" failed job for that folder.

---

## FIX-3 — Exception-safe runner lifecycle  [MED-5 + MED-6]

**Targets selection "Already running" (18×) and stale-closed jobs (40×).**

Strategy: wrap every runner's main entry in `try/finally` that (a) clears `is_running` and (b) writes a terminal job state if one was not already written.

### Pattern to apply to every runner
```python
def run(self, job_id, ...):
    self.is_running = True
    terminal_written = False
    try:
        ...existing body...
        # on normal completion:
        db.update_job_status(job_id, "completed", ...)
        terminal_written = True
    except Exception as e:
        log.exception("Runner %s failed", self.name)
        db.update_job_status(job_id, "failed", str(e)[:500])
        terminal_written = True
        raise
    finally:
        self.is_running = False
        if not terminal_written:
            # Defense against sys.exit / KeyboardInterrupt / thread cancel
            try:
                db.update_job_status(job_id, "failed", "Runner exited without terminal state")
            except Exception:
                pass
```

### Files to touch (grep `is_running = True` across runners)
- `modules/selection.py` — confirmed primary offender
- `modules/engine.py` (scoring runner)
- `modules/tagging.py` (keywords runner)
- `modules/clustering.py`
- `modules/bird_species.py` (if it owns its own runner loop)
- `modules/pipeline.py` / `modules/pipeline_orchestrator.py` (dispatcher-level wrapper)

Prefer a single helper in `modules/pipeline.py` that every runner subclasses / wraps through, rather than copy-pasting the `try/finally` six times.

### Verification
- Start a selection run, kill the process with Ctrl-C mid-run.
- Restart webui. Try a new selection run. Expect no "Already running" error.
- Check `SELECT COUNT(*) FROM jobs WHERE status='running' AND started_at < NOW() - INTERVAL '5 min'` stays at 0 (modulo genuinely long jobs).

---

## FIX-4 — Orphan stacks sweep  [LOW-9]

File: add a function to `modules/db_legacy.py` (or wherever stacks live) and call it from the existing maintenance cycle.

```python
def delete_orphan_stacks():
    return get_connector().execute("""
        DELETE FROM stacks
         WHERE NOT EXISTS (SELECT 1 FROM images WHERE images.stack_id = stacks.id)
    """)
```

Trigger from the nightly maintenance path. One-off drain via `execute_sql` on startup to clear the 12,364 backlog.

### Verification
- Pre: `SELECT COUNT(*) FROM stacks WHERE NOT EXISTS (SELECT 1 FROM images WHERE images.stack_id = stacks.id)` → 12364.
- Post: 0.
- Re-run `check_database_health`; the 12,364-orphan warning is gone.

---

## FIX-5 — Correct debug.log path in MCP  [LOW-11]

File: `modules/mcp_server.py` (grep for `/app/.cursor/debug.log`). Replace the hard-coded container path with a repo-relative resolution:

```python
from modules.config import BASE_DIR
DEBUG_LOG_PATH = os.path.join(BASE_DIR, ".cursor", "debug.log")
```

### Verification
- `read_debug_log` returns entries instead of `Debug log file not found`.

---

## Out of scope for this plan

- **KoniQ/PAQ2PiQ backfill (MED-7)** — not a bug, a product decision. Needs a separate decision doc before any code change.
- **`/api/health` timeout (LOW-10)** — handler is already O(1) (reads in-memory runner refs, no DB). The 10s timeout was most likely contention with the busy dispatcher at probe time. Monitor; only intervene if it recurs on an idle server.
- **`update_job_phase_state` / `log_job_event` (HIGH-2)** and **`MultiModelMUSIQ.load_model` (HIGH-3)** — historical, no live code path. Keep an eye on `get_error_summary` over the next week.

---

## Rollout order

1. FIX-1 (Change A alone drains the backlog; Change B is cheap insurance).
2. Manual reset of the 7 looping folders' `is_fully_scored` flag.
3. FIX-4 one-off sweep.
4. FIX-2 (prevents new path-not-found failures).
5. FIX-3 (largest blast radius; ship behind a test that kills the runner mid-job).
6. FIX-5 (trivial; batch with any of the above PRs).

## Commit hygiene

Separate commits / PRs for FIX-1, FIX-2, FIX-3, FIX-4, FIX-5. Each should be easy to revert in isolation. Touch only the files listed; no drive-by reformatting of `db_legacy.py`.
