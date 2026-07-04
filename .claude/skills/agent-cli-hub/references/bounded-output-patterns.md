# Bounded output patterns

Prefer these over unbounded `cat`, full-tree walks, or dumping entire files.

## Text search (backend defaults)

```bash
rg "SomeSymbol" . \
  --glob '!node_modules' \
  --glob '!static/app' \
  --glob '!FirebirdLinux' \
  --glob '!__pycache__' \
  -n --max-count 50
```

```powershell
rg "SomeSymbol" modules/ -n --max-count 50
```

## Find files

```bash
fd "pattern" modules/ -t f
tree -L 3 modules/ -I '__pycache__|node_modules|static'
```

## Read file slices

```bash
sed -n '1,160p' modules/example.py
bat --line-range 1:160 modules/example.py
```

```powershell
Get-Content .\modules\example.py -TotalCount 160
```

## Git (before and after edits)

```bash
git status --short
git diff --stat
git diff -- modules/example.py | delta
```

## Config inspection

```bash
jq '.scripts' package.json 2>/dev/null || true
python -c "import json; print(list(json.load(open('config.json')).keys())[:20])"
```

Never paste full `config.json` or `.env` if they may contain credentials.

## fff MCP (when connected)

When user-level **fff** MCP is connected, prefer `ffgrep` / `fffind` / `fff-multi-grep` for repeated repo search instead of unbounded shell grep loops. Still cap what you paste into agent responses.

## Dry-run / check modes

```bash
python scripts/doctor.py --no-gpu
docker compose config
ruff check modules/ --output-format=concise
```
