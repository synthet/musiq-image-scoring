# Task Environment and Package Tools

## Purpose
Use repo-defined task runners and language package managers safely.

## When to Use
Use for builds, tests, linting, and local environment setup after inspecting project files.

## Required Tools
just, mise, direnv, uv, ruff, pyright, node, pnpm, corepack, docker compose.

## Install

### Windows PowerShell
```powershell
winget install Casey.Just
winget install jdx.mise
winget install direnv.direnv
winget install OpenJS.NodeJS.LTS
corepack enable
corepack prepare pnpm@latest --activate
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
uv tool install ruff
uv tool install pyright
winget install Docker.DockerDesktop
```

### WSL2 Ubuntu
```bash
sudo apt update
sudo apt install -y direnv docker-compose-v2
curl -LsSf https://astral.sh/uv/install.sh | sh
curl https://mise.run | sh
sudo apt install -y just || true
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt install -y nodejs
corepack enable
corepack prepare pnpm@latest --activate
uv tool install ruff
uv tool install pyright
```

### macOS
```bash
brew install just mise direnv uv ruff pyright node pnpm docker docker-compose
```

## Common Commands
```bash
fd "justfile|mise.toml|package.json|pyproject.toml|docker-compose.yml" .
just --list
mise tasks
jq ".scripts" package.json
uv run pytest -q
pnpm test
docker compose ps
```

## Agent-Safe Patterns
Prefer repo task runners (`just`, `mise run`, npm scripts, Makefile). Use lockfiles and frozen installs where available. Bound test runs to relevant files when possible.

## Commands Requiring Confirmation
Require confirmation for dependency upgrades, lockfile regeneration unrelated to task, Docker volume removal, migrations, publishing packages, and global installs beyond setup.

## Troubleshooting
direnv requires `direnv allow` after reviewing `.envrc`. In WSL2 use Linux Docker integration. Avoid sharing node_modules between Windows and WSL2.

## Verification Checklist
```bash
just --version || true
mise --version || true
direnv version
uv --version
ruff --version
pyright --version
node --version
pnpm --version
docker compose version
```
