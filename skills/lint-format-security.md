# Lint Format Security

## Purpose
Run formatters, linters, shell/Docker checks, and local secret/vulnerability scans.

## When to Use
Use before finalizing changes or when editing shell, Docker, JS/TS, Python, or config files.

## Required Tools
ruff, pyright, shellcheck, shfmt, prettier, eslint, hadolint, trivy, gitleaks.

## Install

### Windows PowerShell
```powershell
uv tool install ruff
uv tool install pyright
winget install koalaman.shellcheck
winget install mvdan.shfmt
winget install OpenJS.NodeJS.LTS
npm i -g prettier eslint
winget install hadolint.hadolint
winget install AquaSecurity.Trivy
winget install gitleaks.gitleaks
```

### WSL2 Ubuntu
```bash
sudo apt update
sudo apt install -y shellcheck
uv tool install ruff
uv tool install pyright
go install mvdan.cc/sh/v3/cmd/shfmt@latest || true
npm i -g prettier eslint
curl -sSfL https://raw.githubusercontent.com/hadolint/hadolint/master/hadolint | sudo tee /usr/local/bin/hadolint >/dev/null && sudo chmod +x /usr/local/bin/hadolint || true
```

### macOS
```bash
brew install ruff pyright shellcheck shfmt hadolint trivy gitleaks node
npm i -g prettier eslint
```

## Common Commands
```bash
ruff check .
pyright
shellcheck scripts/*.sh
shfmt -d scripts/*.sh
prettier --check .
eslint .
hadolint Dockerfile
gitleaks detect --no-banner --redact --exit-code 1
```

## Agent-Safe Patterns
Run check modes before write modes. Prefer project-configured commands. Redact secret scanner output. Limit scans to repo paths.

## Commands Requiring Confirmation
Require confirmation for formatter write modes over large trees, security scans uploading data, auto-fix across repo, and dependency vulnerability remediation.

## Troubleshooting
Pre-existing lint failures are common; report them separately from introduced failures. On Windows, some shell tools work better in WSL2.

## Verification Checklist
```bash
ruff --version
pyright --version
shellcheck --version
shfmt --version
prettier --version
eslint --version
hadolint --version
trivy --version
gitleaks version
```
