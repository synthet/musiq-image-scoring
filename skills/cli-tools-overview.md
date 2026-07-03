# CLI Tools Overview

## Purpose
Choose low-memory CLI tools for repository inspection, editing, verification, and agent handoffs.

## When to Use
Use at the start of any coding task to inspect the repo before assuming language, framework, or workflow.

## Required Tools
git, rg, fd, bat, jq, yq, ast-grep, just/mise, uv/pnpm, docker, shellcheck/shfmt/prettier/eslint, gitleaks/trivy.

## Install

### Windows PowerShell
```powershell
winget install Git.Git
winget install BurntSushi.ripgrep.MSVC
winget install sharkdp.fd
winget install jqlang.jq
winget install sharkdp.bat
winget install GitHub.cli
winget install dandavison.delta
winget install OpenJS.NodeJS.LTS
```

### WSL2 Ubuntu
```bash
sudo apt update
sudo apt install -y git curl jq ripgrep fd-find shellcheck sqlite3 direnv
npm i -g @ast-grep/cli
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### macOS
```bash
brew install git ripgrep fd jq bat shellcheck sqlite direnv gh git-delta ast-grep uv just mise
```

## Common Commands
```bash
git status --short
fd "pyproject.toml|package.json|Cargo.toml|go.mod|justfile|Makefile" .
rg "TODO|FIXME" . --glob '!node_modules' --glob '!target' --glob '!build'
tree -L 3 -I 'node_modules|target|build|dist|.git'
git diff --stat
```

## Agent-Safe Patterns
Prefer discovery commands first. Keep output bounded with `--max-count`, `--max-filesize`, `--line-number`, `sed -n`, `bat --line-range`, and `tree -L`. Use project task runners before ad hoc compiler/test commands.

## Commands Requiring Confirmation
Require confirmation for `rm -rf`, `git reset --hard`, `git clean`, `git filter-repo`, force pushes, Docker volume deletion, database migrations, package upgrades, and secret scanning that uploads data.

## Troubleshooting
If Windows tools are missing from PATH, restart PowerShell or use Scoop shims. In WSL2, install tools inside the distro, not only on Windows. Use `fdfind` alias if Ubuntu packages fd as `fdfind`.

## Verification Checklist
```bash
git --version
rg --version
fd --version || fdfind --version
jq --version
```
