# Manual checks

This directory contains **manual verification scripts** that are intentionally **not** part of automated `pytest` collection.

## Why this folder exists

Some scripts:
- require local DB state,
- mutate DB/filesystem state,
- or are exploratory diagnostics.

Those should not run in automated test pipelines.

## Current scripts moved from `tests/`

- `verify_db_mapping.py`
- `verify_db_null.py`
- `verify_pipeline.py`
- `verify_culling_fix.py`

## Running a manual check

From repo root:

```bash
python manual-checks/verify_pipeline.py
```

Use these only when you explicitly want a manual verification run.
