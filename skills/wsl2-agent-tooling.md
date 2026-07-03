# WSL2 Agent Tooling

## Purpose
Use WSL2 Ubuntu as the default low-friction environment for Linux-like build, test, search, and MCP workflows.

## When to Use
Use for Bash-heavy repos, Docker Compose, Java/Node/Python monorepos, Unix-path MCP servers, CI-like local reproduction, and tools with weaker native Windows support.

## Required Tools
Ubuntu packages, git, rg, fd/fdfind, jq/yq, curl, uv, Node/pnpm, ast-grep, just, mise, docker CLI integration.

## Install

### Windows PowerShell
```powershell
wsl --install -d Ubuntu
wsl -d Ubuntu
```

### WSL2 Ubuntu
```bash
sudo apt update
sudo apt install -y git curl jq ripgrep fd-find shellcheck sqlite3 direnv build-essential ca-certificates
mkdir -p ~/.local/bin
ln -sf $(command -v fdfind) ~/.local/bin/fd
curl -LsSf https://astral.sh/uv/install.sh | sh
curl https://mise.run | sh
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt install -y nodejs
corepack enable
corepack prepare pnpm@latest --activate
npm i -g @ast-grep/cli
```

### macOS
```bash
brew install git curl jq ripgrep fd shellcheck sqlite direnv uv mise node ast-grep just
```

## Common Commands
```bash
git status --short
fd "pyproject.toml|package.json|justfile|Makefile" .
rg "SomeSymbol" . --glob "!node_modules" --glob "!target" --glob "!build"
sed -n "1,160p" path/to/file.py
bat --line-range 1:160 path/to/file.py
docker compose ps
```

## Agent-Safe Patterns
Keep repositories in the Linux filesystem, e.g. `~/src/repo`, not `/mnt/c`, for speed and file semantics. Bound searches and exclude generated directories.

## Commands Requiring Confirmation
Require confirmation for sudo changes outside install steps, deleting files, Docker volume/container prune, database reset, filesystem permission repair, or modifying `/etc` config.

## Troubleshooting
If `fd` is missing, Ubuntu names it `fdfind`; create a symlink. If Docker is unavailable, enable Docker Desktop WSL integration or install native Docker. Avoid mixing Windows and Linux node_modules.

## Verification Checklist
```bash
uname -a
git --version
rg --version
fd --version || fdfind --version
node --version
pnpm --version
docker compose version
```
