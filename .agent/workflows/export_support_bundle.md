---
description: Export redacted support bundle for debugging
---

## Purpose

Create a **redacted** diagnostic zip suitable for maintainers, without hand-collecting logs.

## When to use

- Handoff to another engineer; GitHub issue with diagnostics; comparing environments.

## Canonical docs first

- [docs/DIAGNOSTICS.md](../../docs/DIAGNOSTICS.md)
- [.agent/INFRA_QUICKSTART.md](../INFRA_QUICKSTART.md)
- `scripts/export_debug_bundle.py` (~ same as MCP tool `export_debug_bundle`)

## Safe command

```bash
source ~/.venvs/tf/bin/activate
python scripts/export_debug_bundle.py
```

Optional output path if script supports it (see `--help`).

## Checks

- Open the zip locally; confirm `secrets.json` is **not** inside.
- Redact any remaining sensitive paths before uploading to a public ticket.

## Do not

- Do not attach bundles to public forums without review.
- Do not substitute ad-hoc `tar` of the whole repo for the supported script unless explicitly requested.
