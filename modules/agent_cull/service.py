"""Orchestration for agent-assisted cull review."""

from __future__ import annotations

import json
import logging
from typing import Any

from modules.agent_cull.apply import persist_failed_review, persist_validated_review
from modules.agent_cull.batching import (
    merge_validated_batch_responses,
    plan_review_batches,
    subset_review_unit,
)
from modules.agent_cull.cli_adapter import (
    AgentCullProvider,
    build_prompt,
    classify_cli_process_failure,
    get_provider,
)
from modules.agent_cull.config import AgentCullConfig, load_agent_cull_config
from modules.agent_cull.discovery import ReviewUnit
from modules.agent_cull.payload import build_review_packet, enrich_unit_rows
from modules.agent_cull.safety import apply_safety_gates
from modules.agent_cull.schema import validate_raw_agent_response

logger = logging.getLogger(__name__)


def _run_agent_batch(
    unit: ReviewUnit,
    rows_by_id: dict[int, dict[str, Any]],
    cfg: AgentCullConfig,
    *,
    provider: AgentCullProvider,
    dry_run: bool,
) -> dict[str, Any]:
    """Single agent call for one review unit (may be a batch subset)."""
    packet = build_review_packet(
        unit,
        rows_by_id,
        cfg,
        score_warnings=enrich_unit_rows(rows_by_id, cfg),
    )
    prompt = build_prompt(packet, cfg)
    raw = provider.run_review(prompt, cfg)
    if not raw.ok:
        error_code, error_message = classify_cli_process_failure(
            int(raw.exit_code),
            raw.stderr or "",
            stdout=raw.stdout or "",
        )
        return {
            "ok": False,
            "packet": packet,
            "error_code": error_code,
            "error_message": error_message[:4000],
            "raw_stdout": raw.stdout,
        }

    validation = validate_raw_agent_response(
        raw.stdout,
        stack_id=unit.stack_id,
        sub_stack_id=unit.sub_stack_id,
        rejected_image_ids=set(unit.rejected_ids),
        picked_image_ids=set(unit.picked_ids),
        all_image_ids=set(unit.image_ids),
        require_vision_evidence=(
            cfg.review_picked_quality and cfg.agent.require_vision_evidence
        ),
    )
    if not validation.ok or validation.data is None:
        return {
            "ok": False,
            "packet": packet,
            "error_code": validation.error_code or "schema_invalid",
            "error_message": validation.error_message or "invalid agent response",
            "validation_errors": validation.errors,
            "raw_stdout": raw.stdout,
        }

    return {
        "ok": True,
        "packet": packet,
        "validated": validation.data,
        "raw_stdout": raw.stdout,
        "supports_vision": raw.supports_vision,
        "provider_name": raw.provider or provider.name,
    }


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
    if provider is None:
        provider = get_provider(cfg, override=provider_override)

    batch_plan = plan_review_batches(
        unit,
        rows_by_id,
        batch_size=cfg.review_batch_size,
    )
    batch_results: list[dict[str, Any]] = []
    for batch_ids in batch_plan:
        batch_unit = (
            subset_review_unit(unit, batch_ids)
            if len(batch_plan) > 1
            else unit
        )
        result = _run_agent_batch(
            batch_unit,
            rows_by_id,
            cfg,
            provider=provider,
            dry_run=dry_run,
        )
        if not result["ok"]:
            group_id = persist_failed_review(
                unit=unit,
                packet=result.get("packet"),
                dry_run=dry_run,
                error_code=result.get("error_code") or "agent_failed",
                error_message=result.get("error_message") or "agent batch failed",
                raw_response=result.get("raw_stdout"),
            )
            out: dict[str, Any] = {
                "ok": False,
                "group_id": group_id,
                "error": result.get("error_code"),
            }
            if result.get("validation_errors"):
                out["validation_errors"] = result["validation_errors"]
            if result.get("error_message"):
                out["error_message"] = result["error_message"]
            return out
        batch_results.append(result)

    if len(batch_results) == 1:
        validated = batch_results[0]["validated"]
        raw_response = batch_results[0]["raw_stdout"] or ""
        supports_vision = bool(batch_results[0].get("supports_vision"))
        provider_name = str(batch_results[0].get("provider_name") or provider.name)
        audit_packet = batch_results[0]["packet"]
    else:
        validated = merge_validated_batch_responses(
            [r["validated"] for r in batch_results],
            stack_id=unit.stack_id,
            sub_stack_id=unit.sub_stack_id,
        )
        raw_response = json.dumps(
            [r.get("raw_stdout") or "" for r in batch_results],
            ensure_ascii=False,
        )[:500_000]
        supports_vision = any(bool(r.get("supports_vision")) for r in batch_results)
        provider_name = str(batch_results[0].get("provider_name") or provider.name)
        audit_packet = build_review_packet(
            unit,
            rows_by_id,
            cfg,
            score_warnings=enrich_unit_rows(rows_by_id, cfg),
        )
        audit_packet["review_batches"] = len(batch_plan)
        audit_packet["review_batch_size"] = cfg.review_batch_size

    safety = apply_safety_gates(
        cfg=cfg,
        validated_response=validated,
        rows_by_id=rows_by_id,
        picked_ids=set(unit.picked_ids),
        rejected_ids=set(unit.rejected_ids),
        dry_run=dry_run,
        provider_supports_vision=supports_vision,
    )
    group_id = persist_validated_review(
        unit=unit,
        packet=audit_packet,
        validated=validated,
        safety=safety,
        cfg=cfg,
        dry_run=dry_run,
        rows_by_id=rows_by_id,
        raw_response=raw_response,
        provider_name=provider_name,
        provider_supports_vision=supports_vision,
    )
    return {
        "ok": True,
        "group_id": group_id,
        "dry_run": dry_run,
        "group_decision_allowed": safety.group_decision_allowed,
        "removable_count": sum(1 for d in safety.image_decisions if d.final_decision == "remove"),
        "batch_count": len(batch_plan),
    }
