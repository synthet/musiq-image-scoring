"""Guard tests for the agent cull API-output vocabulary.

These keep ``modules/agent_cull/vocab.py`` honest against the code that
actually emits the values and against ``schema.py``. If an emitting path adds a
new value, the corresponding assertion fails until ``vocab.py`` (and the doc /
gallery type sync) are updated.
"""

from modules.agent_cull import vocab
from modules.agent_cull.apply import (
    PICK_QUALITY_ADVISORY_STATUS,
    candidate_status_for_decision,
)
from modules.agent_cull.operator import APPROVABLE_STATUSES
from modules.agent_cull.schema import ALLOWED_DECISIONS, ALLOWED_GROUP_DECISIONS


def test_output_vocabulary_keys():
    vocabulary = vocab.output_vocabulary()
    assert set(vocabulary) == {
        "candidate_status",
        "agent_decision",
        "final_decision",
        "group_status",
        "group_decision",
    }


def test_candidate_statuses_cover_emitters():
    # Statuses produced by apply.py.
    assert candidate_status_for_decision("remove", dry_run=True) in vocab.CANDIDATE_STATUSES
    assert candidate_status_for_decision("remove", dry_run=False) in vocab.CANDIDATE_STATUSES
    assert candidate_status_for_decision("keep", dry_run=False) in vocab.CANDIDATE_STATUSES
    assert PICK_QUALITY_ADVISORY_STATUS in vocab.CANDIDATE_STATUSES
    # Operator action statuses + the prerequisites they consume.
    assert "operator_approved" in vocab.CANDIDATE_STATUSES
    assert "operator_rejected" in vocab.CANDIDATE_STATUSES
    assert APPROVABLE_STATUSES <= set(vocab.CANDIDATE_STATUSES)


def test_decision_vocab_supersets_agent_schema():
    # The agent may emit any ALLOWED_DECISIONS value as agent_decision; advisory
    # is an additional backend-applied marker.
    assert ALLOWED_DECISIONS <= set(vocab.AGENT_DECISIONS)
    assert "advisory" in vocab.AGENT_DECISIONS
    # final_decision is never upgraded to remove and advisories persist keep, so
    # advisory must NOT leak into the final_decision space.
    assert ALLOWED_DECISIONS <= set(vocab.FINAL_DECISIONS)
    assert "advisory" not in vocab.FINAL_DECISIONS


def test_group_decisions_match_schema():
    assert set(vocab.GROUP_DECISIONS) == set(ALLOWED_GROUP_DECISIONS)


def test_group_statuses_cover_emitters():
    import inspect

    from modules.agent_cull import apply, repository, rollback

    # The insert default (``discovered``) plus every literal status written by
    # the apply/rollback paths must be in GROUP_STATUSES.
    default = inspect.signature(repository.insert_review_group).parameters["status"].default
    emitted = {default}
    for mod in (apply, rollback):
        src = inspect.getsource(mod)
        for token in ("validated", "proposed", "failed", "applied", "rolled_back"):
            if f'status="{token}"' in src or f"status='{token}'" in src:
                emitted.add(token)
    assert emitted <= set(vocab.GROUP_STATUSES), emitted - set(vocab.GROUP_STATUSES)
