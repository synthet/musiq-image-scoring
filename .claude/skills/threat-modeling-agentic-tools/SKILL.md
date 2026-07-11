---
name: threat-modeling-agentic-tools
description: Threat-model agentic tooling — MCP/tool abuse, hook/prompt injection, remote control surfaces, and secret leakage. Use during security reviews or when adding features that expose the system to AI agents or remote callers.
---

# Threat modeling (agentic tools)

## Use this skill when

- Security reviews, or new features touching MCP servers, tools, hooks, or any remote-control surface
- Writing or updating security docs
- Running `/security-review` or reviewing compact MCP `dispatch` actions

## Procedure

1. Read [.agent/SAFETY.md](../../../.agent/SAFETY.md) and `docs/technical/MCP_SEARCH_DISPATCH.md`.
2. **Enumerate assets:** secrets/tokens, credentials, workspace files, agent sessions, audit logs,
   PostgreSQL data, any data the tools can read or mutate.
3. **Enumerate threats** (adapt to your surfaces):
   - Compromised caller / session hijack → access bypass? (mitigate: pairing/allowlist, auth, rate limits)
   - Local network or co-tenant attacker → exposed RPC/endpoint? (mitigate: localhost bind, bearer token)
   - Malicious tool caller → arbitrary operations? (mitigate: tool allowlist, `confirmed=True` gate, no raw shell tools)
   - Hook / prompt / payload **injection** → RCE or unintended action? (mitigate: validate input, no `eval`, minimal hook scripts)
   - Log / output **exfiltration** → secrets in logs or tool output? (mitigate: redaction, never return secrets)
   - Callback / request **replay** → duplicate side effects? (mitigate: nonce, expiry, idempotency)
4. Document **fail-closed** behavior for each path (deny on doubt).
5. List **known limitations** explicitly.

## Safety checks

- Every new external input has a validation schema and an abuse note.
- Explicit approval required for high-risk / side-effecting action types (`ALLOWED_SIDE_EFFECT_ACTIONS`).

## Done criteria

- Review output lists threats, mitigations, gaps, and recommended tests.
- No undocumented secret-storage locations; secrets never appear in logs or tool output.
