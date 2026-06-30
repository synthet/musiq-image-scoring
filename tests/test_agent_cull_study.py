"""Tests for agent cull study harness (mode profiles, probe, prompt selection)."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

from modules.agent_cull.cli_adapter import build_prompt
from modules.agent_cull.config import AgentCullAgentConfig, AgentCullConfig
from modules.agent_cull.mode_profiles import (
    STUDY_MODE_IDS,
    apply_mode_profile,
    resolve_prompt_template_version,
)
from modules.agent_cull.payload import build_review_packet, enrich_unit_rows
from modules.agent_cull.discovery import ReviewUnit


def test_study_mode_ids_complete():
    assert "baseline_v2" in STUDY_MODE_IDS
    assert "metadata_only" in STUDY_MODE_IDS


def test_apply_mode_profile_vision_strict():
    cfg = apply_mode_profile(AgentCullConfig(), "vision_strict")
    assert cfg.agent.prompt_template_version == "cull_redundancy_v3_vision_strict"
    assert cfg.agent.require_vision_evidence is True


def test_production_defaults_v3_vision_and_picked_quality():
    from modules.agent_cull.config import PROMPT_TEMPLATE_VERSION

    assert PROMPT_TEMPLATE_VERSION == "cull_redundancy_v3_vision_strict"
    cfg = AgentCullConfig()
    assert cfg.review_picked_quality is True
    assert cfg.agent.require_vision_evidence is True
    assert cfg.agent.timeout_seconds == 180
    assert resolve_prompt_template_version(cfg) == "cull_redundancy_v3_vision_strict"


def test_build_prompt_includes_picked_audit_when_enabled():
    cfg = apply_mode_profile(AgentCullConfig(), "vision_strict")
    prompt = build_prompt({"schema_version": "agent-cull-request-v1"}, cfg)
    assert "picked_image_advisories" in prompt
    assert "Picked-image quality audit" in prompt


def test_build_prompt_omits_picked_audit_when_disabled():
    cfg = replace(apply_mode_profile(AgentCullConfig(), "vision_strict"), review_picked_quality=False)
    prompt = build_prompt({"schema_version": "agent-cull-request-v1"}, cfg)
    assert "picked_image_advisories" not in prompt


def test_apply_mode_profile_metadata_only_disables_thumbnails():
    cfg = apply_mode_profile(AgentCullConfig(), "metadata_only")
    assert cfg.agent.include_thumbnails is False


def test_apply_mode_profile_technical_focus_flattens_models():
    cfg = apply_mode_profile(AgentCullConfig(), "technical_focus")
    assert "topiq" in cfg.agent.flatten_model_scores
    assert "spaq" in cfg.agent.flatten_model_scores


def test_resolve_prompt_template_version_override():
    cfg = AgentCullConfig(agent=AgentCullAgentConfig(prompt_template_version="cull_redundancy_v3_clip_gate"))
    assert resolve_prompt_template_version(cfg, override=None) == "cull_redundancy_v3_clip_gate"
    assert resolve_prompt_template_version(cfg, override="cull_redundancy_v2") == "cull_redundancy_v2"


def test_build_prompt_loads_v3_template():
    cfg = apply_mode_profile(AgentCullConfig(), "score_first")
    prompt = build_prompt({"schema_version": "agent-cull-request-v1"}, cfg)
    assert "score-first study mode" in prompt.lower() or "score-first" in prompt.lower()
    assert "agent-cull-request-v1" in prompt


def test_build_prompt_unknown_template_raises():
    cfg = replace(
        AgentCullConfig(),
        agent=replace(AgentCullAgentConfig(), prompt_template_version="does_not_exist"),
    )
    with pytest.raises(FileNotFoundError):
        build_prompt({}, cfg)


def test_packet_uses_resolved_thumbnail_path_for_manifest(tmp_path, monkeypatch):
    thumb = tmp_path / "t.jpg"
    thumb.write_bytes(b"\xff\xd8\xff\xd9")
    wsl_path = "/mnt/d/Projects/image-scoring-backend/thumbnails/x/y.jpg"

    import modules.thumbnails as thumb_mod

    monkeypatch.setattr(thumb_mod, "THUMB_DIR", str(tmp_path))
    monkeypatch.setattr(
        thumb_mod,
        "_resolve_thumbnail_filesystem_path",
        lambda tp, tw=None: str(thumb) if tp == wsl_path else tp,
    )

    unit = ReviewUnit(
        review_unit_key="stack_1",
        stack_id=1,
        sub_stack_id=None,
        image_ids=(10,),
        picked_ids=(10,),
        rejected_ids=(),
        neutral_ids=(),
        usable_ids=(10,),
        hierarchy_tier="stack",
    )
    rows = {
        10: {
            "id": 10,
            "file_name": "DSC_0001.NEF",
            "thumbnail_path": wsl_path,
            "score_general": 0.8,
            "score_technical": 0.8,
            "score_aesthetic": 0.8,
            "score": 0.8,
            "pick_status": 1,
        }
    }
    cfg = AgentCullConfig(agent=AgentCullAgentConfig(include_thumbnails=True, include_all_model_scores=False))
    enrich_unit_rows(rows, cfg)
    packet = build_review_packet(unit, rows, cfg)
    assert len(packet["thumbnail_manifest"]) == 1
    assert packet["thumbnail_manifest"][0]["path"] == str(thumb)
    assert os.path.isfile(packet["thumbnail_manifest"][0]["path"])


def test_probe_script_importable():
    script = Path(__file__).resolve().parents[1] / "scripts/study/agent_cull_probe.py"
    assert script.is_file()


def test_mode_profile_metadata_ab_differs_from_baseline():
    base = apply_mode_profile(AgentCullConfig(), "baseline_v2")
    meta = apply_mode_profile(AgentCullConfig(), "metadata_only")
    assert base.agent.include_thumbnails != meta.agent.include_thumbnails


def test_build_prompt_uses_picked_audit_snippet_override():
    cfg = replace(
        apply_mode_profile(AgentCullConfig(), "vision_strict"),
        picked_audit_snippet="picked_quality_audit_snippet_strict_v1.txt",
    )
    prompt = build_prompt({"schema_version": "agent-cull-request-v1"}, cfg)
    assert "MANDATORY checklist" in prompt


def test_apply_mode_profile_strict_picks():
    cfg = apply_mode_profile(AgentCullConfig(), "technical_focus_strict_picks")
    assert cfg.picked_audit_snippet == "picked_quality_audit_snippet_strict_v2.txt"
    assert cfg.agent.prompt_template_version == "cull_redundancy_v3_technical_focus"
    assert cfg.agent.require_vision_evidence is True


def test_build_picked_quality_hints_watchlist():
    from modules.agent_cull.picked_quality_hints import build_picked_quality_hints

    rows = {
        195193: {"score_technical": 0.834, "model_scores": {"clip_quality_v0": 0.551}},
        195199: {"score_technical": 0.72, "model_scores": {"clip_quality_v0": 0.62}},
    }
    images = [
        {
            "id": 195193,
            "file_name": "DSC_8825.NEF",
            "scores": {"score_technical": 0.834, "clip_quality_v0": 0.551, "topiq": 0.55},
        },
        {
            "id": 195199,
            "file_name": "DSC_8831.NEF",
            "scores": {"score_technical": 0.72, "clip_quality_v0": 0.62, "topiq": 0.68},
        },
    ]
    hints = build_picked_quality_hints(
        picked_ids=[195193, 195199],
        rows_by_id=rows,
        images_payload=images,
    )
    assert hints is not None
    assert 195193 in hints["score_technical_watchlist"]
    assert "195193" in hints.get("pairwise_sharper_picked", {})


def test_packet_includes_picked_quality_hints_when_enabled():
    unit = ReviewUnit(
        review_unit_key="stack_29157",
        stack_id=29157,
        sub_stack_id=72253,
        image_ids=(195193, 195199),
        picked_ids=(195193, 195199),
        rejected_ids=(),
        neutral_ids=(),
        usable_ids=(195193, 195199),
        hierarchy_tier="stack",
    )
    rows = {
        195193: {
            "id": 195193,
            "file_name": "a.NEF",
            "score_technical": 0.834,
            "score_general": 0.8,
            "model_scores": {"clip_quality_v0": 0.551},
            "pick_status": 1,
        },
        195199: {
            "id": 195199,
            "file_name": "b.NEF",
            "score_technical": 0.72,
            "score_general": 0.78,
            "model_scores": {"clip_quality_v0": 0.62},
            "pick_status": 1,
        },
    }
    cfg = replace(AgentCullConfig(), review_picked_quality=True, picked_quality_hints=True)
    enrich_unit_rows(rows, cfg)
    packet = build_review_packet(unit, rows, cfg)
    assert "picked_quality_hints" in packet
    assert 195193 in packet["picked_quality_hints"]["score_technical_watchlist"]


def test_build_picked_only_packet():
    from modules.agent_cull.picked_audit import build_picked_only_packet

    unit = ReviewUnit(
        review_unit_key="stack_1",
        stack_id=1,
        sub_stack_id=None,
        image_ids=(10, 20),
        picked_ids=(10,),
        rejected_ids=(20,),
        neutral_ids=(),
        usable_ids=(10, 20),
        hierarchy_tier="stack",
    )
    rows = {
        10: {"id": 10, "file_name": "pick.NEF", "score_general": 0.8, "pick_status": 1},
        20: {"id": 20, "file_name": "rej.NEF", "score_general": 0.7, "pick_status": 0},
    }
    cfg = AgentCullConfig(agent=AgentCullAgentConfig(include_thumbnails=False))
    packet = build_picked_only_packet(unit, rows, cfg)
    assert packet["rejected_image_ids"] == []
    assert packet["picked_image_ids"] == [10]
    assert len(packet["images"]) == 1
    assert packet["images"][0]["id"] == 10


def test_score_picked_advisory_metrics():
    from modules.agent_cull.study_evidence import score_picked_advisory_metrics

    live = {
        "picked_image_advisories": [
            {"image_id": 195193, "issue": "misfocus", "reason": "soft fawn foreground"},
        ],
        "watchlist": [195193],
    }
    m = score_picked_advisory_metrics(live)
    assert m["advisory_count"] == 1
    assert m["195193_advised"] is True
    assert m["195193_misfocus"] is True
    assert m["watchlist_hit"] is True
    assert m["advisory_gap"] is False

    gap = score_picked_advisory_metrics({"watchlist": [195193], "picked_image_advisories": []})
    assert gap["advisory_gap"] is True


def test_matrix_vision_evidence_scoring():
    from modules.agent_cull.study_evidence import score_vision_evidence

    probe = {"ok": True}
    smoke = {"ok": True, "has_visual_language": True}
    live = {"vision_used": True, "viewed_image_ids": [1, 2]}
    ev = score_vision_evidence(probe, smoke, live)
    assert ev["verified"] is True

    ev2 = score_vision_evidence({"ok": False}, None, None)
    assert ev2["verified"] is False
