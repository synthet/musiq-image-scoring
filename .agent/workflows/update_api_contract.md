---
description: Update REST API contract artifacts after code changes
---

## Purpose

Keep **REST behavior**, **OpenAPI**, and **written API contract** aligned when endpoints change.

## When to use

- New route, changed request/response, deprecated field, or OpenAPI regeneration.

## Canonical docs first

- [docs/technical/API_CONTRACT.md](../../docs/technical/API_CONTRACT.md)
- [docs/reference/api/openapi.yaml](../../docs/reference/api/openapi.yaml)
- [docs/reference/api/API_SCHEMA_IMPLEMENTATION.md](../../docs/reference/api/API_SCHEMA_IMPLEMENTATION.md)
- `modules/api.py`

## Safe order

1. Implement or fix behavior in `modules/api.py` (and related modules).
2. Regenerate or hand-edit OpenAPI per project convention (see API_SCHEMA_IMPLEMENTATION).
3. Update **API_CONTRACT.md** to match shipped behavior.
4. If gallery consumes the API: follow [cross_repo_contract_change.md](cross_repo_contract_change.md).
5. Append [docs/log.md](../../docs/log.md).

## Checks

- Gallery: `npm run contract:check` in sibling repo when types are generated from OpenAPI.
- Backend tests touching API: targeted `pytest` under `tests/`.

## Do not

- Do not document endpoints that are not implemented, or omit breaking changes from API_CONTRACT.
