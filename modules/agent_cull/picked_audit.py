"""Picked-only audit pass (study / two-pass runner)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from modules.agent_cull.config import AgentCullConfig
from modules.agent_cull.discovery import ReviewUnit
from modules.agent_cull.json_util import json_dumps
from modules.agent_cull.mode_profiles import resolve_prompt_template_version
from modules.agent_cull.payload import build_review_packet, enrich_unit_rows


def build_picked_only_packet(
    unit: ReviewUnit,
    rows_by_id: dict[int, dict[str, Any]],
    cfg: AgentCullConfig,
) -> dict[str, Any]:
    """Subset packet containing only picked images for pass-2 advisory audit."""
    picked = set(unit.picked_ids)
    sub_rows = {iid: rows_by_id[iid] for iid in unit.picked_ids if iid in rows_by_id}
    sub_unit = ReviewUnit(
        review_unit_key=unit.review_unit_key,
        stack_id=unit.stack_id,
        sub_stack_id=unit.sub_stack_id,
        image_ids=tuple(unit.picked_ids),
        picked_ids=unit.picked_ids,
        rejected_ids=(),
        neutral_ids=(),
        usable_ids=tuple(iid for iid in unit.picked_ids if iid in unit.usable_ids),
        hierarchy_tier=unit.hierarchy_tier,
    )
    score_warnings = enrich_unit_rows(sub_rows, cfg)
    packet = build_review_packet(sub_unit, sub_rows, cfg, score_warnings=score_warnings)
    packet["rejected_image_ids"] = []
    packet["images"] = [img for img in packet.get("images") or [] if int(img.get("id", -1)) in picked]
    packet["thumbnail_manifest"] = [
        m
        for m in packet.get("thumbnail_manifest") or []
        if int(m.get("image_id", -1)) in picked
    ]
    packet["policy"] = {
        **(packet.get("policy") or {}),
        "picked_audit_only": True,
        "note": "Return rejected_image_decisions as [] and focus on picked_image_advisories.",
    }
    return packet


def build_picked_audit_prompt(packet: dict[str, Any], cfg: AgentCullConfig) -> str:
    prompts_dir = Path(__file__).resolve().parent / "prompts"
    template = (prompts_dir / "picked_audit_only.txt").read_text(encoding="utf-8")
    return template + "\n" + json_dumps(packet)


def run_picked_audit_pass(
    unit: ReviewUnit,
    rows_by_id: dict[int, dict[str, Any]],
    cfg: AgentCullConfig,
    *,
    provider_override: str | None = None,
) -> dict[str, Any]:
    """Second-pass CLI call: picked-only advisory audit."""
    from modules.agent_cull.cli_adapter import get_provider
    from modules.agent_cull.schema import validate_raw_agent_response

    packet = build_picked_only_packet(unit, rows_by_id, cfg)
    prompt = build_picked_audit_prompt(packet, cfg)
    provider = get_provider(cfg, override=provider_override)
    raw = provider.run_review(prompt, cfg)
    if not raw.ok:
        return {
            "ok": False,
            "error": "cli_failed",
            "exit_code": raw.exit_code,
            "stderr_head": (raw.stderr or "")[:500],
        }
    validation = validate_raw_agent_response(
        raw.stdout,
        stack_id=unit.stack_id,
        sub_stack_id=unit.sub_stack_id,
        rejected_image_ids=set(),
        picked_image_ids=set(unit.picked_ids),
        all_image_ids=set(unit.picked_ids),
        require_vision_evidence=cfg.agent.require_vision_evidence,
    )
    if not validation.ok or validation.data is None:
        return {
            "ok": False,
            "error": validation.error_code or "validation_failed",
            "validation_errors": validation.errors,
            "stdout_head": (raw.stdout or "")[:2000],
        }
    data = validation.data
    advisories = data.get("picked_image_advisories") or []
    return {
        "ok": True,
        "vision_used": data.get("vision_used"),
        "viewed_image_ids": data.get("viewed_image_ids"),
        "picked_image_advisories": advisories,
        "advisory_count": len(advisories),
        "prompt_template_version": resolve_prompt_template_version(cfg),
    }
