"""Tests for agent cull local safety gates."""

from dataclasses import replace

from modules.agent_cull.config import AgentCullAgentConfig, AgentCullConfig
from modules.agent_cull.safety import apply_safety_gates


def _cfg() -> AgentCullConfig:
    return AgentCullConfig()


def _cfg_no_vision_gate() -> AgentCullConfig:
    """Default config but with the (now default-on) vision-evidence gate off,
    so tests can isolate non-vision gates without supplying viewed_image_ids."""
    return replace(
        AgentCullConfig(),
        agent=replace(AgentCullAgentConfig(), require_vision_evidence=False),
    )


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
        cfg=_cfg_no_vision_gate(),
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


def test_require_vision_evidence_blocks_without_viewed_ids():
    cfg = AgentCullConfig(agent=replace(AgentCullAgentConfig(), require_vision_evidence=True))
    safety = apply_safety_gates(
        cfg=cfg,
        validated_response=_response(),
        rows_by_id={
            100: {"score_general": 0.2, "usable": True},
            101: {"score_general": 0.9, "usable": True},
        },
        picked_ids={101},
        rejected_ids={100},
        dry_run=True,
        provider_supports_vision=True,
    )
    assert safety.group_blocked is True
    assert safety.image_decisions[0].final_decision == "keep"
    group_gates = {o.gate for o in safety.overrides if o.scope == "group"}
    assert "vision_not_used" in group_gates


def test_picked_advisories_do_not_block_group():
    # Advisories live outside rejected_image_decisions; safety must ignore them
    # and never let them affect the group/remove gates.
    resp = _response()
    resp["picked_image_advisories"] = [
        {
            "image_id": 101,
            "issue": "misfocus",
            "reason": "soft foreground",
            "suggested_alternatives": [],
            "risk_flags": ["foreground_soft"],
        }
    ]
    safety = apply_safety_gates(
        cfg=_cfg_no_vision_gate(),
        validated_response=resp,
        rows_by_id={
            100: {"score_general": 0.2, "usable": True},
            101: {"score_general": 0.9, "usable": True},
        },
        picked_ids={101},
        rejected_ids={100},
        dry_run=True,
        provider_supports_vision=True,
    )
    assert safety.group_blocked is False
    # Only the rejected image is gated; the advised pick is untouched.
    assert {d.image_id for d in safety.image_decisions} == {100}
    assert safety.image_decisions[0].final_decision == "remove"


def test_require_vision_evidence_allows_when_viewed():
    cfg = AgentCullConfig(agent=replace(AgentCullAgentConfig(), require_vision_evidence=True))
    resp = _response()
    resp["vision_used"] = True
    resp["viewed_image_ids"] = [100, 101]
    safety = apply_safety_gates(
        cfg=cfg,
        validated_response=resp,
        rows_by_id={
            100: {"score_general": 0.2, "usable": True},
            101: {"score_general": 0.9, "usable": True},
        },
        picked_ids={101},
        rejected_ids={100},
        dry_run=True,
        provider_supports_vision=True,
    )
    assert safety.group_blocked is False
    assert safety.image_decisions[0].final_decision == "remove"
