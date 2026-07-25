# Search tool selection

When to use `rg`, `grep`, `ast-grep`, `fd`, `fzf`, and related tools. Full command examples live in [../SKILL.md](../SKILL.md); bounded output patterns in [agent-cli-hub bounded-output-patterns.md](../../agent-cli-hub/references/bounded-output-patterns.md).

## Decision flow

```text
What are you looking for?
├── File or path by name/extension     → fd
├── Literal text or regex in contents  → rg (ripgrep)
│   └── rg missing?                    → grep (fallback only)
├── Syntax shape / AST pattern         → ast-grep
│   └── security / rule pack scan      → semgrep --dryrun
├── Directory layout only              → tree or eza
└── Too many rg hits?
    ├── Narrow: path prefix, --max-count, -g glob
    └── Human exploratory pick         → fzf (optional; avoid in agent loops)

After locating a file → bat --line-range or sed -n (never unbounded cat)
```

## Tool matrix

| Tool | Use when | Do not use when | Gallery default |
|------|----------|-----------------|-----------------|
| **`rg`** | Repo-wide text/regex; respects `.gitignore`; need line numbers | Single known file (use `bat --line-range`) | **Yes** — first choice for content search |
| **`grep`** | `rg` unavailable; piping one stream; POSIX-only shell | Recursive search on large trees; primary agent workflow | Fallback only |
| **`ast-grep`** | Function/class/JSX **shapes**; refactor targets; regex too brittle | Simple string literals; config/logs; non-code files | After `rg` when pattern is structural |
| **`fd`** | Find files by **name**, extension, or path segment | Search **inside** file contents | Before `rg` when hunting filenames |
| **`fzf`** | Interactive narrowing for a human; pick from long lists | Autonomous agent loops (non-scriptable TUI) | Optional; prefer `rg --max-count` + path |
| **`tree` / `eza`** | Orientation; depth-limited layout | Finding a string inside files | Before first edit in unfamiliar dirs |
| **`bat` / `sed -n`** | Read 80–160 lines **after** locating file | Discovery (use `rg`/`fd` first) | Always bound reads |
| **`semgrep`** | Security/rule packs; org-wide policy checks | Ad hoc symbol lookup | `--dryrun` only unless user asks |
| **`ctags`** | Repeated def/ref across sessions; LSP unavailable | One-off search | Optional index |
| **fff MCP** (`grep`, `find_files`, `multi_grep`) | Repeated repo-wide file/content search when **project** `fff-be` MCP is connected | One-off bounded probe; fff not installed | Prefer over many grep tool roundtrips |
| **Graphify** (`graphify query` / `path` / `explain`) | Cross-module architecture; “how does X connect to Y”; god nodes — when `graphify-out/graph.json` exists | Literal string search; pipeline/DB triage (`is-be-mcp`); no graph built yet | Escalate after `rg`/`fff` for structure |

## fff MCP (when connected)

When **fff** is registered as **`fff-be`** in **project** [`.cursor/mcp.json`](../../../mcp.example.json) with repo `cwd` (see [AGENTS.md § fff](../../../../AGENTS.md)):

- Prefer **`grep`** / **`find_files`** / **`multi_grep`** for repeated repo-wide search.
- Call shapes:
  - `grep({ query: "*.{py,ts} exif_transpose" })` — constraints are **inline** in `query` (no `constraints` param)
  - `find_files({ query: "…" })`
  - `multi_grep({ patterns: ["a", "b"], constraints: "*.{py,ts}" })` — `constraints` is a **string**
- Anti-patterns: do not pass `queries`; do not pass `constraints` to **`grep`**; do not pass `constraints` as an array/object on **`multi_grep`**.
- Keep one-off bounded probes as **`rg`** / **`fd`** (fast, no index warmup).
- Do not replace **`ast-grep`** for syntax-shape queries — fff is text/path indexed search.
- Do **not** put fff in user `~/.cursor/mcp.json` — repo-scoped indexing requires project config.

## Graphify (when installed)

When **`graphifyy`** is on PATH and `graphify-out/graph.json` exists (see [AGENTS.md § Graphify](../../../../AGENTS.md), [`.cursor/rules/graphify.mdc`](../../../rules/graphify.mdc), and skill [`graphify`](../../graphify/SKILL.md)):

- Prefer MCP **`graphify-be`** tools (`query_graph`, `shortest_path`, …) when connected; else CLI **`graphify query`** / **`path`** / **`explain`**.
- Keep literal discovery as **`rg`** / **`fff`**; keep scoring/DB triage on **`is-be-mcp`**.
- Soft rule only (`alwaysApply: false`) — do not run stock `graphify cursor install` (that sets always-on nudge).

## Default order

```text
fd (filename) → rg (content) → ast-grep (syntax) → bat/sed (read slice)
# architecture / connectivity (if graph built):
→ graphify query|path|explain
```

## grep vs ripgrep (`rg`)

| | `grep` | `rg` |
|---|--------|-----|
| Speed on large repos | Slow | Fast |
| Respects `.gitignore` | No (unless configured) | Yes |
| Agent default | No | **Yes** |
| When to use | `rg` not installed; `cmd \| grep` on one stream | Almost all repo content search |

**Anti-pattern:** `grep -r` across the repo root — skips ignore rules, scans `node_modules`, floods context. Use `rg` instead.

Install `rg`: [install-blocks.md](../../agent-cli-hub/references/install-blocks.md).

## ast-grep vs rg

| Question type | Tool |
|---------------|------|
| "Where is the string `useGalleryStore`?" | `rg` |
| "Where is `ipcMain.handle` registered?" | `rg` (literal) or `ast-grep` if matching call shape |
| "Every exported function in `src/`" | `ast-grep` |
| "All React components using `useEffect` without deps array" | `ast-grep` |
| "Find `database.engine` in config" | `rg` or `jq` via [agent-data-config](../../agent-data-config/SKILL.md) |

Use **ast-grep** when regex would match comments/strings incorrectly or when the query is about **syntax**, not text.

## fd vs rg

| Question type | Tool |
|---------------|------|
| "List all `.tsx` under `src/components`" | `fd -e tsx src/components` |
| "Find file named `db.ts`" | `fd db.ts` or `fd -g '**/db.ts'` |
| "Where is `preload.ts` imported?" | `rg "preload" electron/` |

**fd** finds **files**; **rg** finds **content inside** files.

## fzf (agents)

`fzf` is for interactive human narrowing. Autonomous agents should instead:

```bash
rg "pattern" src/ -n --max-count 30
rg "pattern" electron/ -n --max-count 30
```

Use `fzf` only when the user is at the keyboard picking from a long list.

## Cursor IDE equivalents

When running inside Cursor (not shell):

| Shell tool | Cursor alternative | Same rule |
|------------|-------------------|-----------|
| `rg` | **Grep** tool (rg-backed) | Text/regex in repo |
| Meaning-based "how does X work?" | **SemanticSearch** | Not literal string match |
| Filename glob | **Glob** tool | Like `fd` by pattern |

Apply the same decision logic: text → Grep/rg; meaning → SemanticSearch; filename → Glob/fd.

## Gallery examples

| Question | Tool | Example |
|----------|------|---------|
| Where is a function defined? | `rg` | `rg "def process_batch" modules/ -n` |
| All `.py` in modules | `fd` | `fd -e py modules/` |
| Exported class shape | `ast-grep` | `ast-grep --pattern 'class $N' --lang python modules/` |
| What does `modules/` contain? | `tree` | `tree -L 2 modules/` |
| Config key | `rg` or Python | `rg "database" config.json` |

Backend search globs:

```bash
--glob '!__pycache__' --glob '!static/app' --glob '!FirebirdLinux'
```

## Anti-patterns

- Recursive `grep -r .` from repo root
- `cat` on large files before trying `rg` or `fd`
- `ast-grep` for plain string search (overkill)
- `fzf` in unattended agent scripts
- Unbounded `rg` without path prefix or `--max-count`
