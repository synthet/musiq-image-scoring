# Gallery API Types Regeneration

This page describes how **image-scoring-gallery** syncs OpenAPI and generates TypeScript types. The gallery repo is the execution context for these commands.

## Source of truth

The canonical REST contract is backend-generated [openapi.json](../../openapi.json) at the **image-scoring-backend** repository root. Gallery keeps a synced copy at `api-contract/openapi.json`.

Cross-project overview: [technical/OPENAPI_CROSS_PROJECT.md](../technical/OPENAPI_CROSS_PROJECT.md).

## Gallery commands

Run from **image-scoring-gallery** (sibling backend at `../image-scoring-backend`):

```bash
npm run contract:diff          # copy sibling openapi.json → api-contract/
npm run contract:update        # fetch live /openapi.json (fallback to sibling)
npm run contract:check         # verify snapshot is current
npm run generate:api-types     # write electron/api.generated.ts
npm run contract:validate      # coverage vs apiTypes.ts / apiService.ts
```

`generate:api-types` runs `scripts/generate-api-types.mjs`, which invokes `openapi-typescript` on the sibling `openapi.json` and writes **`electron/api.generated.ts`** (not `apiTypes.ts`).

Hand-written types remain in `electron/apiTypes.ts`; migrate consumers incrementally to generated types when touching call sites.

## Backend regeneration

When changing REST routes or models in `modules/api.py`:

```bash
python scripts/export_openapi.py   # backend repo → openapi.json
```

Then re-sync gallery per the commands above.
