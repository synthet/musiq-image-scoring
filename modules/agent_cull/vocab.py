"""Canonical API-output vocabularies for agent cull review.

These are the enum value spaces the backend *serializes to clients* (the
gallery's ``agentCullReview.ts`` consumes them). They are distinct from the
*agent-input* schema in ``docs/technical/AGENT_CULL_REVIEW_SCHEMA.json``, which
describes what the LLM emits — these describe what the backend persists and
returns after safety gating and operator actions.

This module is the single source of truth: ``GET /api/culling/agent-review/
schema`` exposes :func:`output_vocabulary` and
``docs/technical/AGENT_CULL_API_VOCABULARY.md`` documents the same sets. When
the emitting code changes, update the tuples here and both surfaces follow.
"""

from __future__ import annotations

from modules.agent_cull.apply import PICK_QUALITY_ADVISORY_STATUS

# ``agent_cull_recommendations.candidate_status`` — see ``apply.py`` (proposed /
# agent_remove_candidate / pick_quality_advisory) and ``operator.py``
# (operator_approved / operator_rejected). ``rollback.py`` restores the prior
# value rather than introducing a new one, so ``rolled_back`` is NOT a
# recommendation candidate_status (it is only a *group* status, below).
CANDIDATE_STATUSES: tuple[str, ...] = (
    "none",
    "proposed",
    "agent_remove_candidate",
    PICK_QUALITY_ADVISORY_STATUS,
    "operator_approved",
    "operator_rejected",
)

# ``agent_cull_recommendations.agent_decision`` — the raw per-image decision
# (``safety.py``, defaulting to ``uncertain``) plus the advisory marker emitted
# for picked-image quality advisories (``apply.py``).
AGENT_DECISIONS: tuple[str, ...] = (
    "remove",
    "keep",
    "uncertain",
    "advisory",
)

# ``agent_cull_recommendations.final_decision`` — the post-safety decision.
# Safety never upgrades to ``remove``; advisories always persist ``keep``, so
# ``advisory`` never appears here.
FINAL_DECISIONS: tuple[str, ...] = (
    "remove",
    "keep",
    "uncertain",
)

# ``agent_cull_review_groups.status`` lifecycle.
GROUP_STATUSES: tuple[str, ...] = (
    "validated",
    "proposed",
    "failed",
    "applied",
    "rolled_back",
)

# ``agent_cull_review_groups.group_decision`` (may also be ``null`` when no
# removable items survive gating). Mirrors ``schema.ALLOWED_GROUP_DECISIONS``.
GROUP_DECISIONS: tuple[str, ...] = (
    "apply_removals",
    "do_not_apply",
)


def output_vocabulary() -> dict[str, list[str]]:
    """Serializable copy of the API-output enum value spaces."""
    return {
        "candidate_status": list(CANDIDATE_STATUSES),
        "agent_decision": list(AGENT_DECISIONS),
        "final_decision": list(FINAL_DECISIONS),
        "group_status": list(GROUP_STATUSES),
        "group_decision": list(GROUP_DECISIONS),
    }
