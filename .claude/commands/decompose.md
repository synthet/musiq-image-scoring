> **Claude Code:** Same intent as Cursor `/decompose`. When customizing, keep in sync with `.cursor/commands/decompose.md`.

# /decompose — Break a large task into parallel-ready subtasks

Use before `/plan` when a task is too large for a single session or could benefit from
parallel agent execution across independent branches.

## Inputs

- Feature request, issue number, or approved spec.
- Size hint (optional): S / M / L budget per subtask.

## Output

### 1. Subtask list

For each subtask:

| Field | Description |
|-------|-------------|
| **Title** | Short imperative name (e.g. "Add ARNIQA model wrapper") |
| **Done means** | Single-sentence observable outcome |
| **Size** | S (< 1 h), M (1–4 h), L (4–8 h) |
| **Depends on** | Subtask titles this one blocks on, or "none" |

### 2. Dependency graph

ASCII or Mermaid DAG showing which subtasks must be sequential and which are
independent. Example:

```
A ──► C ──► E
B ──┘       │
D ──────────┘
```

### 3. Parallel execution note

Explicitly state which subtasks are independent and safe to run in parallel:

> Subtasks A, B, D are independent. Run as separate branches simultaneously using
> git worktrees or separate sessions. Merge order: A and B before C; D before E.

### 4. Test boundaries

For each subtask, one sentence on how it validates independently (unit test file,
integration check, or manual smoke test) so a partial merge is safe.

## Done when

- Each subtask can be `/plan`-ed independently with no hidden dependencies.
- The dependency graph has no cycles.
- Parallel subtasks are explicitly called out so a fleet of agents can execute them simultaneously.

## Usage pattern

```
/decompose "Add DINOv2 culling space (issue #220)"
→ produces subtask list + dependency graph
/plan <subtask-A>   # in session 1
/plan <subtask-B>   # in session 2 (parallel branch)
```
