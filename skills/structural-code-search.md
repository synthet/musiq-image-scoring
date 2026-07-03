# Structural Code Search

## Purpose
Find and rewrite code by syntax tree rather than plain text.

## When to Use
Use for API migrations, framework patterns, import edits, risky refactors, and language-aware searches.

## Required Tools
ast-grep/sg, semgrep, tree-sitter CLI, universal-ctags.

## Install

### Windows PowerShell
```powershell
winget install semgrep.semgrep
winget install universal-ctags.ctags
npm i -g @ast-grep/cli tree-sitter-cli
```

### WSL2 Ubuntu
```bash
sudo apt update
sudo apt install -y universal-ctags
python3 -m pip install --user semgrep || uv tool install semgrep
npm i -g @ast-grep/cli tree-sitter-cli
```

### macOS
```bash
brew install ast-grep semgrep tree-sitter universal-ctags
```

## Common Commands
```bash
sg run -p "console.log($$$)" -l ts .
sg scan --rule sgconfig.yml
semgrep scan --config auto --max-target-bytes 1000000
ctags -R --languages=Python,JavaScript,TypeScript --exclude=node_modules --exclude=.git .
```

## Agent-Safe Patterns
Start with read-only search. Review matches before applying rewrites. Keep semgrep target size bounded and exclude vendor/build paths.

## Commands Requiring Confirmation
Require confirmation for `sg run --update-all`, semgrep autofix, bulk rewrites, and generated ctags/indices committed to repo.

## Troubleshooting
Windows npm install for ast-grep is usually easiest; Scoop can also work. WSL2 is preferred for large Unix-oriented repos. Semgrep Windows support can lag; use WSL2 if install fails.

## Verification Checklist
```bash
sg --version
semgrep --version
tree-sitter --version
ctags --version
```
