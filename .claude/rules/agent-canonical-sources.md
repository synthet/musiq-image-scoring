---
description: Canonical sources and agent authority for image-scoring-backend
alwaysApply: true
---

# Agent canonical sources (backend)

Before changing **APIs**, **database fields**, **phase names**, **`phase_code` values**, **`config.json` keys**, or **MCP-visible behavior**, confirm facts in the sources below. If a fact is not found, say it is not confirmed—do not invent it.

## Authority stack (read first)

1. [docs/CANONICAL_SOURCES.md](../../docs/CANONICAL_SOURCES.md) — master map
2. [docs/technical/API_CONTRACT.md](../../docs/technical/API_CONTRACT.md) — REST contract
3. [docs/reference/api/openapi.yaml](../../docs/reference/api/openapi.yaml) — OpenAPI artifact
4. [docs/technical/PIPELINE_TERMINOLOGY.md](../../docs/technical/PIPELINE_TERMINOLOGY.md) — UI labels vs `phase_code` vs API job types
5. [docs/technical/DB_SCHEMA.md](../../docs/technical/DB_SCHEMA.md) — PostgreSQL-oriented reference
6. [docs/technical/AGENT_COORDINATION.md](../../docs/technical/AGENT_COORDINATION.md) — cross-repo steps with **image-scoring-gallery**

## Database and vectors

- **PostgreSQL + pgvector** is the primary database engine. **Firebird** is **legacy**—do not describe it as current default (see [docs/DATABASE.md](../../docs/DATABASE.md), [docs/planning/database/FIREBIRD_POSTGRES_MIGRATION.md](../../docs/planning/database/FIREBIRD_POSTGRES_MIGRATION.md)).
- **Embeddings:** default space dimensions and model family are documented in [docs/EMBEDDINGS.md](../../docs/EMBEDDINGS.md) and [docs/technical/EMBEDDINGS.md](../../docs/technical/EMBEDDINGS.md) (e.g. MobileNetV2-style **1280**-dim where stated there).

## Diagnostics (prefer before ad-hoc debugging)

- WSL + `source ~/.venvs/tf/bin/activate` then: `python scripts/doctor.py`, `python scripts/doctor.py --no-gpu`, `python scripts/doctor.py --json`
- Redacted bundle only via: `python scripts/export_debug_bundle.py` — review before sharing; see [.agent/SAFETY.md](../../.agent/SAFETY.md)

## Fast automated check

- `python -m pytest -m "not gpu and not db and not ml and not firebird" --ignore=tests/test_probe.py` (see [AGENTS.md](../../AGENTS.md))

## Agent infra index

- [.agent/AGENT_INFRA_INVENTORY.md](../../.agent/AGENT_INFRA_INVENTORY.md), [.agent/COMMANDS.md](../../.agent/COMMANDS.md), [.agent/SAFETY.md](../../.agent/SAFETY.md), [.agent/workflows/](../../.agent/workflows/)
