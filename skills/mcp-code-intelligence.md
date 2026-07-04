# MCP Code Intelligence

## Purpose
Select code-intelligence MCP approaches from lightweight wrappers to advanced indexing.

## When to Use
Use when an agent needs reusable tools for repo search, symbol lookup, patching, memory, or multi-repo code navigation.

## Required Tools
Raw CLI wrappers over rg/fd/bat/git diff, ast-grep MCP, Serena, codebase-memory-mcp, Zoekt, optional embedding search such as claude-context.

## Install

### Windows PowerShell
```powershell
winget install BurntSushi.ripgrep.MSVC
winget install sharkdp.fd
winget install sharkdp.bat
winget install Git.Git
npm i -g @ast-grep/cli
```

### WSL2 Ubuntu
```bash
sudo apt update
sudo apt install -y git ripgrep fd-find bat
npm i -g @ast-grep/cli
# Serena/codebase-memory/Zoekt: install per official repo, preferably inside WSL2 for Unix paths.
```

### macOS
```bash
brew install git ripgrep fd bat ast-grep zoekt universal-ctags || true
```

## Common Commands
```bash
rg "SomeSymbol" . --json --glob "!node_modules"
fd "Service|Controller" .
bat --line-range 1:160 path/to/file
git diff --stat
sg run -p "if ($COND) { $$$ }" -l ts .
zoekt-git-index -index ~/.zoekt /path/to/repo
zoekt-webserver --index ~/.zoekt -rpc
```

## Agent-Safe Patterns
Minimal MCP: rg + fd + read_file + git diff + patch_file. Better: add ast-grep, git tools, and task runner. Advanced: Serena or codebase-memory-mcp plus Zoekt and optional embeddings. Keep embeddings secondary to text/structural search because indexing is heavier.

## Commands Requiring Confirmation
Require confirmation for write-capable MCP actions, bulk refactors, persistent indexing of private repos, embedding uploads, and any tool that stores code outside the machine.

## Troubleshooting
Raw CLI wrappers are easiest and lowest memory. ast-grep adds structural search/rewrite. ctags/Zoekt provide symbol/text indexing. Serena/codebase-memory provide semantic/graph/memory workflows. Embeddings help fuzzy discovery but can be slow/costly and stale.

## Verification Checklist
```bash
rg --version
fd --version || fdfind --version
sg --version
git --version
ctags --version || true
zoekt-webserver -version || true
```
