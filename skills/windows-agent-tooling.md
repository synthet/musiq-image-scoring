# Windows Agent Tooling

## Purpose
Run agent-friendly commands from native PowerShell while keeping repos and path handling predictable.

## When to Use
Use for Windows-native repos, PowerShell scripts, GitHub CLI operations, simple search/editing, uv Python tools, and Node/pnpm tasks.

## Required Tools
PowerShell 7, winget or scoop, Git for Windows, gh, rg, fd, bat, delta, jq, zoxide, Node LTS, corepack/pnpm, uv.

## Install

### Windows PowerShell
```powershell
winget install Microsoft.PowerShell
winget install Git.Git
winget install GitHub.cli
winget install BurntSushi.ripgrep.MSVC
winget install sharkdp.fd
winget install sharkdp.bat
winget install jqlang.jq
winget install dandavison.delta
winget install ajeetdsouza.zoxide
winget install OpenJS.NodeJS.LTS
corepack enable
corepack prepare pnpm@latest --activate
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### WSL2 Ubuntu
```bash
sudo apt update
sudo apt install -y powershell git curl jq ripgrep fd-find
```

### macOS
```bash
brew install powershell git gh ripgrep fd bat jq git-delta zoxide node uv
```

## Common Commands
```bash
git status --short
rg "SomeSymbol" .
fd "Controller|Service|Repository" .
Get-Content .\path\to\file.java -TotalCount 160
git diff --stat
jq '.scripts' package.json
```

## Agent-Safe Patterns
Use PowerShell paths for Windows-native tools and quote paths with spaces. Keep repo operations in one shell family per task. Run `git status --short` before edits.

## Commands Requiring Confirmation
Do not run `Remove-Item -Recurse -Force`, `git reset --hard`, `git clean -fdx`, `docker system prune`, or registry/profile edits without confirmation.

## Troubleshooting
If `fd` conflicts, call `fd.exe`. Configure Git autocrlf intentionally. Prefer WSL2 for Bash-heavy repos, Unix symlinks, Linux Docker Compose parity, or MCP servers expecting Unix paths.

## Verification Checklist
```bash
$PSVersionTable.PSVersion
git --version
rg --version
fd --version
node --version
pnpm --version
uv --version
```
