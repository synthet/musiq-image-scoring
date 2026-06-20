# Agent-assisted cull review — spec hub

Canonical **implementation spec** for the metadata-only agent cull review MVP.

| Doc | Purpose |
|-----|---------|
| [summary.md](summary.md) | Current architecture, shipped scope, backlog issue map |
| [worklog.md](worklog.md) | Chronological session log (append-only) |
| [Operator: Gemini CLI setup](../../guides/setup/agent-cull-review-gemini-cli.md) | Docker / WSL / Windows `agent.command` paths |

## Related

- Feature overview: [features/planned/agent-assisted-cull-review.md](../../features/planned/agent-assisted-cull-review.md)
- JSON response schema: [technical/AGENT_CULL_REVIEW_SCHEMA.json](../../technical/AGENT_CULL_REVIEW_SCHEMA.json)
- Cross-repo coordination: [technical/AGENT_COORDINATION.md](../../technical/AGENT_COORDINATION.md)
- Gallery operator: [image-scoring-gallery guides/04-agent-cull-review.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/guides/04-agent-cull-review.md)

## GitHub backlog

| Repo | Epic | Children |
|------|------|----------|
| image-scoring-backend | [#253](https://github.com/synthet/image-scoring-backend/issues/253) | [#254](https://github.com/synthet/image-scoring-backend/issues/254)–[#258](https://github.com/synthet/image-scoring-backend/issues/258) |
| image-scoring-gallery | [#134](https://github.com/synthet/image-scoring-gallery/issues/134) | [#135](https://github.com/synthet/image-scoring-gallery/issues/135)–[#137](https://github.com/synthet/image-scoring-gallery/issues/137) |

Project board: https://github.com/users/synthet/projects/1 (filter `cross-repo` + title *agent cull*).
