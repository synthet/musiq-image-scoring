# SKILL.md change review (AST10)

Use when a pull request adds or materially changes a **first-party** agent skill (`**/SKILL.md`). Full enterprise checklist: [OWASP Agentic Skills Top 10 — checklist.md](https://github.com/kenhuangus/agentic-skills-top-10/blob/main/checklist.md). Context: [AST10 README](https://github.com/kenhuangus/agentic-skills-top-10).

Many upstream checks assume **untrusted registry skills** (signing, SBOM, container sandboxes). For **git-reviewed repo skills**, treat the items below as the **minimum** human review. Record completion in the PR thread or checklist.

## Trust and content (AST01, AST04, AST08)

- [ ] **Source:** Changes are authored by trusted contributors; no pasted-in third-party `SKILL.md` without full review.
- [ ] **Prose + code:** Read the entire file (natural language and any fenced commands); no hidden exfil instructions, obfuscated payloads, or unrelated credential access.
- [ ] **Metadata:** `name` / `description` in YAML frontmatter honestly match behavior (no impersonation, no understated risk).

## Supply chain and sync (AST02, AST07, AST10)

- [ ] **Canonical copy:** If the skill exists under `.cursor/skills/<name>/`, that path is **canonical**; `.claude/skills/<name>/SKILL.md` is updated in the **same PR** when applicable (see [AGENTS.md](../AGENTS.md#agent-skills-source-of-truth-ast10)).
- [ ] **Inventory:** [SKILL_INVENTORY.md](./SKILL_INVENTORY.md) updated (new row or **Last reviewed** date).

## Privilege and scope (AST03)

- [ ] **Scope:** Instructions stay within the skill’s stated purpose (backend vs gallery vs docs); no broad “read all secrets” unless justified and called out.
- [ ] **Shell / network / MCP:** New `curl`, download, or credential paths are justified; copy-paste commands use known project hosts/paths only.

## Platform and repo safety (AST05, AST06 — applicable subset)

- [ ] **No unsafe YAML:** Frontmatter stays to plain keys (`name`, `description`, …); no `!!python/object` or exotic YAML tags.
- [ ] **Identity files:** Skill does not instruct writing to unrelated agent identity files (e.g. arbitrary `SOUL.md` / `MEMORY.md`); edits to repo `AGENTS.md` only when the ticket requires it and are explicit in the PR.

## Governance (AST09)

- [ ] **Risk:** Informal tier (L1/L2) in the inventory still matches the skill after the change.

---

*Inventory:* [.agent/SKILL_INVENTORY.md](./SKILL_INVENTORY.md)
