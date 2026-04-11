# Gallery API Types Regeneration

## Source of truth

The canonical API contract source is the backend-generated `openapi.json` at the repository root.

- Input schema: `./openapi.json`
- Generated output: `./electron/apiTypes.ts`

## Deterministic generation path

Use the same command locally and in CI:

```bash
npm run api:types:generate
```

This command executes `scripts/generate-api-types.mjs`, which reads `openapi.json` and rewrites `electron/apiTypes.ts` using pinned `openapi-typescript` output.

## Validation command

To verify committed output is current:

```bash
npm run api:types:check
```

If validation fails, it prints a diff and asks you to re-run `npm run api:types:generate`.
