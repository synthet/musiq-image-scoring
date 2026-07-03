# Safe Command Patterns

## Purpose
Standardize bounded, reversible, low-risk command usage for autonomous agents.

## When to Use
Use before running unfamiliar commands, modifying files, or finalizing work.

## Required Tools
git, rg, fd, bat/sed, jq/yq, task runners, apply_patch or patch_file tools.

## Install

### Windows PowerShell
```powershell
winget install Git.Git
winget install BurntSushi.ripgrep.MSVC
winget install sharkdp.fd
winget install sharkdp.bat
winget install jqlang.jq
```

### WSL2 Ubuntu
```bash
sudo apt update
sudo apt install -y git ripgrep fd-find bat jq
```

### macOS
```bash
brew install git ripgrep fd bat jq
```

## Common Commands
```bash
git status --short
fd "package.json|pyproject.toml|go.mod|Cargo.toml|justfile|Makefile" .
rg "SomeSymbol" . --glob "!node_modules" --glob "!target" --glob "!build"
sed -n "1,160p" path/to/file
git diff --stat
git diff -- path/to/file
```

## Agent-Safe Patterns
Inspect before edit, edit smallest scope, verify with project commands, show diff. Prefer dry-run flags. Use timeouts for hanging tests. Capture only relevant log tails.

## Commands Requiring Confirmation
Require confirmation for destructive deletes, history rewrites, clean/reset, database writes, migrations, credential changes, external uploads, package publish, and Docker prune/volume removal.

## Troubleshooting
If output is too large, rerun with tighter globs, `head`, `--max-count`, or path filters. If a command has no dry-run, do not automate destructive mode.

## Verification Checklist
```bash
git status --short
git diff --stat
rg --version
fd --version || fdfind --version
```
