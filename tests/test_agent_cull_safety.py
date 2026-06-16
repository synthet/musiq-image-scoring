"""Tests for agent cull local safety gates."""

from modules.agent_cull.config import AgentCullConfig
from modules.agent_cull.safety import apply_safety_gates


def _cfg() -> AgentCullConfig:
    return AgentCullConfig()


def _response(*, group_conf=0.9, image_conf=0.9, decision="remove", alts=None):
    alts = alts if alts is not None else [101]
    return {
        "group_decision": "apply_removals",
        "confidence": group_conf,
        "rejected_image_decisions": [
            {
                "image_id": 100,
                "filename": "rej.jpg",
                "decision": decision,
                "confidence": image_conf,
                "reason": "duplicate",
                "better_alternatives": alts,
                "risk_flags": [],
            }
        ],
    }


def test_no_picked_blocks_remove():
    safety = apply_safety_gates(
        cfg=_cfg(),
        validated_response=_response(),
        rows_by_id={100: {"score_general": 0.2, "usable": True}},
        picked_ids=set(),
        rejected_ids={100},
        dry_run=True,
        provider_supports_vision=True,
    )
    assert safety.group_blocked is True
    assert safety.image_decisions[0].final_decision == "keep"


def test_picked_lt_rejected_does_not_block_group():
    safety = apply_safety_gates(
        cfg=_cfg(),
        validated_response=_response(),
        rows_by_id={
            100: {"score_general": 0.2, "usable": True},
            101: {"score_general": 0.9, "usable": True},
            102: {"score_general": 0.1, "usable": True},
        },
        picked_ids={101},
        rejected_ids={100, 102},
        dry_run=True,
        provider_supports_vision=True,
    )
    assert safety.group_blocked is False
    assert safety.image_decisions[0].final_decision == "remove"
    group_gates = {o.gate for o in safety.overrides if o.scope == "group"}
    assert "picked_lt_rejected_advisory" in group_gates


def test_low_confidence_downgrades_remove():
    safety = apply_safety_gates(
        cfg=_cfg(),
        validated_response=_response(image_conf=0.2),
        rows_by_id={
            100: {"score_general": 0.2, "usable": True},
            101: {"score_general": 0.9, "usable": True},
        },
        picked_ids={101},
        rejected_ids={100},
        dry_run=True,
        provider_supports_vision=True,
    )
    assert safety.image_decisions[0].final_decision == "uncertain"


def test_uncertain_agent_decision_kept():
    safety = apply_safety_gates(
        cfg=_cfg(),
        validated_response=_response(decision="uncertain", image_conf=0.95),
        rows_by_id={
            100: {"score_general": 0.2, "usable": True},
            101: {"score_general": 0.9, "usable": True},
        },
        picked_ids={101},
        rejected_ids={100},
        dry_run=True,
        provider_supports_vision=True,
    )
    assert safety.image_decisions[0].final_decision == "uncertain"


def test_higher_rejected_score_blocked():
    safety = apply_safety_gates(
        cfg=_cfg(),
        validated_response=_response(),
        rows_by_id={
            100: {"score_general": 0.95, "usable": True},
            101: {"score_general": 0.5, "usable": True},
        },
        picked_ids={101},
        rejected_ids={100},
        dry_run=True,
        provider_supports_vision=True,
    )
    assert safety.image_decisions[0].final_decision == "keep"


def test_unique_species_blocked():
    safety = apply_safety_gates(
        cfg=_cfg(),
        validated_response=_response(),
        rows_by_id={
            100: {"score_general": 0.2, "keywords": ["species:Eagle"], "usable": True},
            101: {"score_general": 0.9, "keywords": ["species:Hawk"], "usable": True},
        },
        picked_ids={101},
        rejected_ids={100},
        dry_run=True,
        provider_supports_vision=True,
    )
    assert safety.image_decisions[0].final_decision == "keep"


def test_never_upgrades_keep_to_remove():
    safety = apply_safety_gates(
        cfg=_cfg(),
        validated_response=_response(decision="keep"),
        rows_by_id={
            100: {"score_general": 0.2, "usable": True},
            101: {"score_general": 0.9, "usable": True},
        },
        picked_ids={101},
        rejected_ids={100},
        dry_run=True,
        provider_supports_vision=True,
    )
    assert safety.image_decisions[0].final_decision == "keep"


def test_unusable_picked_alternative_blocks_remove():
    safety = apply_safety_gates(
        cfg=_cfg(),
        validated_response=_response(alts=[101]),
        rows_by_id={
            100: {"score_general": 0.2, "usable": True},
            101: {"score_general": 0.9, "usable": False},
        },
        picked_ids={101},
        rejected_ids={100},
        dry_run=True,
        provider_supports_vision=True,
    )
    decision = safety.image_decisions[0]
    assert decision.final_decision == "keep"
    gates = {o.gate for o in decision.safety_overrides}
    assert "alternative_unusable" in gates
