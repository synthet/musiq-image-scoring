# Git and Diff Workflows

## Purpose
Inspect, edit, review, commit, and create PRs safely.

## When to Use
Use before and after every code modification and before final handoff.

## Required Tools
git, gh, delta, git-filter-repo, gitleaks.

## Install

### Windows PowerShell
```powershell
winget install Git.Git
winget install GitHub.cli
winget install dandavison.delta
winget install gitleaks.gitleaks
python -m pip install --user git-filter-repo
```

### WSL2 Ubuntu
```bash
sudo apt update
sudo apt install -y git gh
curl -sSfL https://raw.githubusercontent.com/gitleaks/gitleaks/master/install.sh | sh -s -- -b ~/.local/bin
uv tool install git-filter-repo
```

### macOS
```bash
brew install git gh git-delta git-filter-repo gitleaks
```

## Common Commands
```bash
git status --short
git branch --show-current
git diff --stat
git diff -- path/to/file | delta
git log --oneline -20
gh pr status
```

## Agent-Safe Patterns
Always inspect status before editing. Use path-limited diffs. Commit only intentional files. Prefer `git restore --source=HEAD -- path` only after confirmation.

## Commands Requiring Confirmation
Require confirmation for reset, clean, rebase, filter-repo, force push, branch deletion, tag deletion, and commands touching `.git/config`.

## Troubleshooting
If delta unavailable, plain `git diff -- path` is fine. In WSL2, configure Git identity separately. Never modify `.git/config` in this repo.

## Verification Checklist
```bash
git --version
gh --version
delta --version || true
gitleaks version || true
```
