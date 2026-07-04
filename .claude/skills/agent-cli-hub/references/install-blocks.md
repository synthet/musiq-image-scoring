# Install blocks (shared reference)

Confirm package IDs on locked-down machines with `winget search` or your package manager before installing.

## Windows PowerShell (winget)

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
corepack enable
corepack prepare pnpm@latest --activate
npm i -g @ast-grep/cli
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
uv tool install ruff
uv tool install pyright
```

Scoop alternatives when winget IDs are unavailable:

```powershell
scoop install git gh ripgrep fd jq delta bat zoxide fzf hyperfine
```

## WSL2 Ubuntu

```bash
sudo apt update
sudo apt install -y git curl jq ripgrep fd-find shellcheck sqlite3 direnv
mkdir -p ~/.local/bin && ln -sf /usr/bin/fdfind ~/.local/bin/fd
curl -LsSf https://astral.sh/uv/install.sh | sh
curl https://mise.run | sh
curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to ~/.local/bin
corepack enable
corepack prepare pnpm@latest --activate
npm i -g @ast-grep/cli pyright
uv tool install ruff
```

## macOS (Homebrew)

```bash
brew install git gh ripgrep fd fzf tree eza zoxide bat git-delta jq yq dasel sqlite curlie httpie just mise direnv uv ruff pyright node pnpm ast-grep semgrep tree-sitter universal-ctags shellcheck shfmt prettier eslint hadolint trivy hyperfine entr watchexec watchman
brew install dmtrKovalenko/fff/fff-mcp   # optional — fast agent file search MCP
corepack enable
corepack prepare pnpm@latest --activate
```

## fff MCP (optional, all platforms)

Fast indexed file search for agents — [github.com/dmtrKovalenko/fff](https://github.com/dmtrKovalenko/fff).

```powershell
# Windows
irm https://raw.githubusercontent.com/dmtrKovalenko/fff/main/install-mcp.ps1 | iex
```

```bash
# Linux / macOS
curl -L https://dmtrkovalenko.dev/install-fff-mcp.sh | bash
```

Wire into user `~/.cursor/mcp.json` — see [`.cursor/mcp.user.example.json`](../../../.cursor/mcp.user.example.json).

## Verification

```bash
git --version
rg --version
fd --version || fdfind --version
jq --version
node --version
corepack --version
```

PowerShell:

```powershell
Get-Command rg, fd, git, jq, node
```
