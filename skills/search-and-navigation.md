# Search and Navigation

## Purpose
Fast repo navigation and bounded text/file discovery.

## When to Use
Use whenever locating symbols, files, configs, tests, docs, or call sites before editing.

## Required Tools
rg, fd, fzf, tree, eza, zoxide, bat.

## Install

### Windows PowerShell
```powershell
winget install BurntSushi.ripgrep.MSVC
winget install sharkdp.fd
winget install junegunn.fzf
winget install GnuWin32.Tree
winget install eza-community.eza
winget install sharkdp.bat
winget install ajeetdsouza.zoxide
```

### WSL2 Ubuntu
```bash
sudo apt update
sudo apt install -y ripgrep fd-find fzf tree bat zoxide
sudo mkdir -p /usr/local/bin; sudo ln -sf /usr/bin/fdfind /usr/local/bin/fd || true
```

### macOS
```bash
brew install ripgrep fd fzf tree eza bat zoxide
```

## Common Commands
```bash
rg "SomeSymbol" . --glob "!node_modules" --glob "!target" --glob "!build"
rg --files | head -200
fd "Controller|Service|Repository" .
tree -L 3 -I "node_modules|target|build|dist|.git"
bat --line-range 1:160 path/to/file
sed -n "1,160p" path/to/file
```

## Agent-Safe Patterns
Use ignore files by default; add `--hidden` only when needed and pair with `--glob !.git`. Pipe through `head` or use `--max-count` for broad searches.

## Commands Requiring Confirmation
Do not run unrestricted recursive output commands like full `tree`, `cat **/*`, or `rg .` at repo root without bounds.

## Troubleshooting
PowerShell: `Get-Content .\path\file -TotalCount 160`. WSL2/Linux: prefer `fd`/`rg` inside the distro. If colors pollute logs, add `--color never`.

## Verification Checklist
```bash
rg --version
fd --version || fdfind --version
fzf --version
tree --version
bat --version
```
