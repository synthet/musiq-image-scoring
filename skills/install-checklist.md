# Install Checklist

## Purpose
Ready-to-run bootstrap blocks for common agent CLI tooling.

## When to Use
Use to set up a new Windows, WSL2 Ubuntu, or macOS machine for coding-agent work.

## Required Tools
Core search/navigation, Git/GitHub, data tools, Node/pnpm, uv/ruff/pyright, ast-grep, just/mise/direnv, Docker, lint/security tools.

## Install

### Windows PowerShell
```powershell
winget install Git.Git
winget install GitHub.cli
winget install BurntSushi.ripgrep.MSVC
winget install sharkdp.fd
winget install jqlang.jq
winget install dandavison.delta
winget install sharkdp.bat
winget install ajeetdsouza.zoxide
winget install OpenJS.NodeJS.LTS
winget install Casey.Just
winget install jdx.mise
winget install direnv.direnv
winget install Docker.DockerDesktop
winget install koalaman.shellcheck
winget install mvdan.shfmt
winget install AquaSecurity.Trivy
winget install gitleaks.gitleaks
corepack enable
corepack prepare pnpm@latest --activate
npm i -g @ast-grep/cli prettier eslint
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
uv tool install ruff
uv tool install pyright
```

### WSL2 Ubuntu
```bash
sudo apt update
sudo apt install -y git curl jq ripgrep fd-find shellcheck sqlite3 direnv build-essential ca-certificates
mkdir -p ~/.local/bin
ln -sf $(command -v fdfind) ~/.local/bin/fd || true
curl -LsSf https://astral.sh/uv/install.sh | sh
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt install -y nodejs
corepack enable
corepack prepare pnpm@latest --activate
npm i -g @ast-grep/cli prettier eslint
curl https://mise.run | sh
sudo apt install -y just || true
uv tool install ruff
uv tool install pyright
```

### macOS
```bash
brew install git gh ripgrep fd jq git-delta bat zoxide node just mise direnv docker shellcheck shfmt trivy gitleaks uv ast-grep sqlite httpie yq
corepack enable
corepack prepare pnpm@latest --activate
uv tool install ruff
uv tool install pyright
```

## Common Commands
```bash
git --version
rg --version
fd --version || fdfind --version
jq --version
bat --version
node --version
pnpm --version
uv --version
ruff --version
pyright --version
sg --version
```

## Agent-Safe Patterns
Run installer blocks interactively. Re-run idempotent version checks after opening a new shell. Prefer WSL2 for repo work and Windows host for IDEs and Docker Desktop.

## Commands Requiring Confirmation
Do not pipe installer scripts without reviewing in high-security environments. Require confirmation before changing shell profile, enabling direnv, or installing global npm/uv tools on shared machines.

## Troubleshooting
If winget IDs change, search with `winget search <name>`. If apt packages lag, use official project installers. If corporate proxy blocks downloads, use approved mirrors.

## Verification Checklist
```bash
git --version
rg --version
fd --version || fdfind --version
gh --version
node --version
pnpm --version
uv --version
sg --version
```
