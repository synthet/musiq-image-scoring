# Commands requiring confirmation

Do **not** run these automatically. Ask the user first unless they explicitly requested the operation.

## Deleting or overwriting

- `rm -rf`, `del /s`, `git clean`, `git reset --hard`
- Mass `mv` or generated-file purges

## History / repo rewrites

- `git filter-repo`, interactive `git rebase`, `git push --force`
- Branch deletion on shared remotes

## Security / network-heavy

- `gitleaks` or credential scans against third-party targets without scope approval
- Posting config or secrets to external services

## Auto-fixers (touch many files)

- `eslint --fix`, `prettier --write`, `ruff --fix`
- `semgrep --autofix`, `ast-grep -U`, codemods

## Gallery-specific

- `npm run build` packaging (large artifact) when user only asked for a code review
- Modifying `config.json` connection strings or database credentials

See also [`.agent/SAFETY.md`](../../../../.agent/SAFETY.md) for IPC, secrets, and renderer boundary rules.
