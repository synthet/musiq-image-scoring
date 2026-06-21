# Runs monitoring snapshot — 2026-06-17

Point-in-time capture of `/ui/runs` and backing APIs while auto-drive was active on WebUI port **7860**.

## Data sources

| Source | Endpoint / tool |
|--------|-----------------|
| Drive loop | `GET /api/runs/drive/status` |
| Active + queue | `GET /api/tasks/active` |
| Run stages | `GET /api/runs/{id}/stages` |
| Run diagnostics | MCP `jobs.get_run_diagnostics` |
| Audit volume | SQL `SELECT COUNT(*) FROM auditlog WHERE run_id = ?` |
| Job inventory | SQL on `jobs`, `job_phases` |

## Auto-drive

- **Enabled**: yes (`limit=50`, `max_repeats=2`, all target phases including `bird_species`).
- **Outstanding folders**: 7 — `awaiting_metadata: 2`, `in_flight: 5`.
- **Last batch**: scheduled 2 folder runs; self-heal maintenance `heal_thumbnails` (job **4170**).
- **Asset gaps**: 8,400 thumbnail gaps, 551 EXIF-date gaps.

## Dispatcher (snapshot time)

- **Active runner**: `metadata` on job **4168** (`/mnt/d/Photos/Z8/180-600mm/2025/2025-11-09`).
- **Queued**: **4169** (metadata multi-phase, `2025-11-11`), **4170** (maintenance).
- **Run 4168 metadata progress**: 124 IPS `done`, 1 `running`; **412** `auditlog` rows for `run_id=4168`.

## Critical finding: phantom `running` job phases

Six `jobs.status='running'` rows; only one runner busy:

| Job | Folder | `job_phases` stuck | Runner |
|-----|--------|-------------------|--------|
| 4162–4166 | 2026 date folders | `keywords` = `running` | tagging **idle** |
| 4168 | 2025-11-09 | `metadata` = `running` | metadata **busy** |

**Root cause**: [`dequeue_next_job`](../../modules/db_legacy.py) ran before [`get_running_job_for_phase_continuation`](../../modules/db_legacy.py), starting newer queued work while older multi-phase jobs retained stale `job_phases.state='running'` without an active runner.

**Remediation** (this change set): `reconcile_phantom_running_job_phases`, continuation-first dispatch, `dispatcher.max_in_flight_jobs`, and `auto_drive.max_in_flight_jobs`.

## Monitoring playbook

```bash
# Active snapshot
curl -s http://127.0.0.1:7860/api/tasks/active
curl -s http://127.0.0.1:7860/api/runs/drive/status

# Watch one run
python scripts/watch_run_http.py 4168 --verbose --interval 5

# MCP (is-be-mcp)
# dispatch("jobs.get_run_diagnostics", {"run_id": 4168})
# dispatch("logs.search_logs", {"pattern": "DISPATCHER|runs_autodrive"})
```

See [DIAGNOSTICS.md](../DIAGNOSTICS.md) and [RUNS_WALKTHROUGH.md](../technical/RUNS_WALKTHROUGH.md).

## Related reports

- [RUN_ORCHESTRATION_AUDIT_2026-04-17.md](RUN_ORCHESTRATION_AUDIT_2026-04-17.md)
- [UI_RUNS_CODE_REVIEW_2026-04-18.md](UI_RUNS_CODE_REVIEW_2026-04-18.md)
