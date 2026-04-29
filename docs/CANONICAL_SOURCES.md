# Canonical sources for agents and implementers

Use these as the authority before inventing API shapes, phase names, or schema details.

| Topic | Canonical location |
|--------|---------------------|
| REST contract and response models | [`technical/API_CONTRACT.md`](technical/API_CONTRACT.md), [`reference/api/openapi.yaml`](reference/api/openapi.yaml), [`reference/api/API.md`](reference/api/API.md) |
| Pipeline vocabulary (UI vs `phase_code` vs REST) | [`technical/PIPELINE_TERMINOLOGY.md`](technical/PIPELINE_TERMINOLOGY.md) |
| Database tables and columns | [`technical/DB_SCHEMA.md`](technical/DB_SCHEMA.md), Alembic under [`../migrations/versions/`](../migrations/versions/) |
| Cross-repo coordination (gallery + backend) | [`technical/AGENT_COORDINATION.md`](technical/AGENT_COORDINATION.md) |
| Open work and priorities | Repository root [`../TODO.md`](../TODO.md), [`planning/INDEX.md`](planning/INDEX.md) |
| Wiki structure and maintenance | [`WIKI_SCHEMA.md`](WIKI_SCHEMA.md), [`log.md`](log.md) |
| Shared UI palette, Lucide icon contract (`/ui/` + Electron gallery) | [`design/DESIGN_SYSTEM.md`](design/DESIGN_SYSTEM.md) (`frontend/src/index.css`, gallery `tokens.css`) |
| Local diagnostics, doctor CLI, redacted support bundles | [`DIAGNOSTICS.md`](DIAGNOSTICS.md), [`.agent/INFRA_QUICKSTART.md`](../.agent/INFRA_QUICKSTART.md), `scripts/doctor.py`, `scripts/export_debug_bundle.py` (see also [DEVELOPMENT.md](DEVELOPMENT.md), [TESTING.md](TESTING.md)) |

**See also:** [Documentation README](README.md) · [Full index](INDEX.md)
