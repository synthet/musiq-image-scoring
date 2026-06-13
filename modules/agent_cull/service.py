"""Orchestration for agent-assisted cull review."""

from __future__ import annotations

import logging
from typing import Any

from modules.agent_cull.apply import persist_failed_review, persist_validated_review
from modules.agent_cull.cli_adapter import AgentCullProvider, build_prompt, get_provider
from modules.agent_cull.config import AgentCullConfig, load_agent_cull_config
from modules.agent_cull.discovery import ReviewUnit
from modules.agent_cull.payload import build_review_packet
from modules.agent_cull.safety import apply_safety_gates
from modules.agent_cull.schema import validate_raw_agent_response

logger = logging.getLogger(__name__)


def run_agent_review_for_unit(
    unit: ReviewUnit,
    rows_by_id: dict[int, dict[str, Any]],
    cfg: AgentCullConfig | None = None,
    *,
    dry_run: bool | None = None,
    provider: AgentCullProvider | None = None,
    provider_override: str | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_agent_cull_config()
    dry_run = cfg.dry_run_default if dry_run is None else dry_run

    packet = build_review_packet(unit, rows_by_id, cfg)
    if provider is None:
        provider = get_provider(cfg, override=provider_override)

    prompt = build_prompt(packet)
    raw = provider.run_review(prompt, cfg)
    if not raw.ok and not raw.stdout:
        group_id = persist_failed_review(
            unit=unit,
            packet=packet,
            dry_run=dry_run,
            error_code=raw.error or "agent_failed",
            error_message=raw.stderr or "agent invocation failed",
            raw_response=raw.stdout,
        )
        return {"ok": False, "group_id": group_id, "error": raw.error or "agent_failed"}

    validation = validate_raw_agent_response(
        raw.stdout,
        stack_id=unit.stack_id,
        sub_stack_id=unit.sub_stack_id,
        rejected_image_ids=set(unit.rejected_ids),
        picked_image_ids=set(unit.picked_ids),
    )
    if not validation.ok or validation.data is None:
        group_id = persist_failed_review(
            unit=unit,
            packet=packet,
            dry_run=dry_run,
            error_code=validation.error_code or "schema_invalid",
            error_message=validation.error_message or "invalid agent response",
            raw_response=raw.stdout,
        )
        return {
            "ok": False,
            "group_id": group_id,
            "error": validation.error_code,
            "validation_errors": validation.errors,
        }

    safety = apply_safety_gates(
        cfg=cfg,
        validated_response=validation.data,
        rows_by_id=rows_by_id,
        picked_ids=set(unit.picked_ids),
        rejected_ids=set(unit.rejected_ids),
        dry_run=dry_run,
        provider_supports_vision=raw.supports_vision,
    )
    group_id = persist_validated_review(
        unit=unit,
        packet=packet,
        validated=validation.data,
        safety=safety,
        cfg=cfg,
        dry_run=dry_run,
        rows_by_id=rows_by_id,
        raw_response=raw.stdout,
        provider_name=raw.provider or provider.name,
        provider_supports_vision=raw.supports_vision,
    )
    return {
        "ok": True,
        "group_id": group_id,
        "dry_run": dry_run,
        "group_decision_allowed": safety.group_decision_allowed,
        "removable_count": sum(1 for d in safety.image_decisions if d.final_decision == "remove"),
    }
