# Canonical sources for agents and implementers

Use these as the authority before inventing API shapes, phase names, or schema details.

| Topic | Canonical location |
|--------|---------------------|
| REST contract and response models | [`technical/API_CONTRACT.md`](technical/API_CONTRACT.md), [`reference/api/openapi.yaml`](reference/api/openapi.yaml), [`reference/api/API.md`](reference/api/API.md) |
| Pipeline vocabulary (UI vs `phase_code` vs REST) | [`technical/PIPELINE_TERMINOLOGY.md`](technical/PIPELINE_TERMINOLOGY.md) |
| Runs submit execution options (`run_mode`, validation-repair) | [`technical/RUN_OPTIONS_MODE_MATRIX.md`](technical/RUN_OPTIONS_MODE_MATRIX.md) |
| Database tables and columns | [`technical/DB_SCHEMA.md`](technical/DB_SCHEMA.md), Alembic under [`../migrations/versions/`](../migrations/versions/) |
| Cross-repo coordination (gallery + backend) | [`technical/AGENT_COORDINATION.md`](technical/AGENT_COORDINATION.md) |
| Gallery **Sync from device** → Postgres IPS / `jobs` | [`technical/ELECTRON_SYNC_IMPORT_AND_PHASES.md`](technical/ELECTRON_SYNC_IMPORT_AND_PHASES.md) · **Gallery workflow:** [06-sync-from-device-workflow.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/features/implemented/06-sync-from-device-workflow.md) |
| Open work and priorities | Repository root [`../TODO.md`](../TODO.md), [`planning/INDEX.md`](planning/INDEX.md) |
| Wiki structure and maintenance | [`WIKI_SCHEMA.md`](WIKI_SCHEMA.md), [`log.md`](log.md) |
| Shared UI palette, Lucide icon contract (`/ui/` + Electron gallery) | [`design/DESIGN_SYSTEM.md`](design/DESIGN_SYSTEM.md) (`frontend/src/index.css`, gallery `tokens.css`) |
| Local diagnostics, doctor CLI, redacted support bundles | [`DIAGNOSTICS.md`](DIAGNOSTICS.md), [`.agent/INFRA_QUICKSTART.md`](../.agent/INFRA_QUICKSTART.md), `scripts/doctor.py`, `scripts/export_debug_bundle.py` (see also [DEVELOPMENT.md](DEVELOPMENT.md), [TESTING.md](TESTING.md)) |

**See also:** [Documentation README](README.md) · [Full index](INDEX.md)
