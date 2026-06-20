"""Deterministic local safety gates for agent cull recommendations."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from modules.agent_cull.config import AgentCullConfig


@dataclass
class SafetyOverride:
    gate: str
    scope: str  # "group" | "image"
    image_id: int | None = None
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"gate": self.gate, "scope": self.scope}
        if self.image_id is not None:
            out["image_id"] = self.image_id
        if self.detail:
            out["detail"] = self.detail
        return out


@dataclass
class GatedImageDecision:
    image_id: int
    agent_decision: str
    final_decision: str
    confidence: float | None
    reason: str
    better_alternatives: list[int]
    risk_flags: list[str]
    safety_overrides: list[SafetyOverride] = field(default_factory=list)


@dataclass
class SafetyResult:
    group_blocked: bool
    group_decision_allowed: bool
    overrides: list[SafetyOverride] = field(default_factory=list)
    image_decisions: list[GatedImageDecision] = field(default_factory=list)


def _best_score(rows_by_id: dict[int, dict[str, Any]], ids: list[int], field_name: str) -> float | None:
    values: list[float] = []
    for iid in ids:
        row = rows_by_id.get(iid) or {}
        val = row.get(field_name)
        if val is None:
            continue
        try:
            f = float(val)
            if not math.isnan(f):
                values.append(f)
        except (TypeError, ValueError):
            continue
    return max(values) if values else None


def _species_tags(keywords: list[str]) -> set[str]:
    return {k for k in keywords if k.lower().startswith("species:")}


def _keywords_for_row(row: dict[str, Any]) -> list[str]:
    raw = row.get("keywords") or []
    if isinstance(raw, str):
        return [k.strip() for k in raw.split(",") if k.strip()]
    if isinstance(raw, list):
        return [str(k).strip() for k in raw if str(k).strip()]
    return []


def apply_safety_gates(
    *,
    cfg: AgentCullConfig,
    validated_response: dict[str, Any],
    rows_by_id: dict[int, dict[str, Any]],
    picked_ids: set[int],
    rejected_ids: set[int],
    dry_run: bool,
    provider_supports_vision: bool,
) -> SafetyResult:
    overrides: list[SafetyOverride] = []
    group_blocked = False

    if len(picked_ids) < 1:
        overrides.append(SafetyOverride("no_picked_images", "group"))
        group_blocked = True
    if len(picked_ids) < len(rejected_ids):
        overrides.append(SafetyOverride("picked_lt_rejected_advisory", "group"))

    group_conf = float(validated_response.get("confidence") or 0.0)
    if group_conf < cfg.min_group_confidence:
        overrides.append(SafetyOverride("group_confidence_low", "group", detail=str(group_conf)))
        group_blocked = True

    if not provider_supports_vision and not cfg.allow_metadata_only_remove:
        overrides.append(SafetyOverride("metadata_only_remove_disabled", "group"))
        group_blocked = True

    if cfg.agent.require_vision_evidence and provider_supports_vision:
        vision_used = validated_response.get("vision_used")
        viewed_ids: set[int] = set()
        raw_viewed = validated_response.get("viewed_image_ids")
        if isinstance(raw_viewed, list):
            for vid in raw_viewed:
                try:
                    viewed_ids.add(int(vid))
                except (TypeError, ValueError):
                    pass
        if vision_used is not True:
            overrides.append(SafetyOverride("vision_not_used", "group"))
            group_blocked = True
        else:
            for item in validated_response.get("rejected_image_decisions") or []:
                if str(item.get("decision") or "") != "remove":
                    continue
                try:
                    iid = int(item.get("image_id"))
                except (TypeError, ValueError):
                    continue
                if iid not in viewed_ids:
                    overrides.append(SafetyOverride("image_not_viewed", "group", image_id=iid))
                    group_blocked = True

    if dry_run:
        overrides.append(SafetyOverride("dry_run", "group"))

    group_decision = validated_response.get("group_decision")
    if group_decision != "apply_removals":
        overrides.append(SafetyOverride("agent_group_do_not_apply", "group"))
        group_blocked = True

    # Precompute species uniqueness within group
    all_ids = picked_ids | rejected_ids
    species_by_image: dict[int, set[str]] = {
        iid: _species_tags(_keywords_for_row(rows_by_id.get(iid) or {})) for iid in all_ids
    }
    species_counts: dict[str, int] = {}
    for tags in species_by_image.values():
        for tag in tags:
            species_counts[tag] = species_counts.get(tag, 0) + 1

    keyword_counts: dict[str, int] = {}
    for iid in all_ids:
        for kw in _keywords_for_row(rows_by_id.get(iid) or {}):
            keyword_counts[kw] = keyword_counts.get(kw, 0) + 1

    image_decisions: list[GatedImageDecision] = []
    for item in validated_response.get("rejected_image_decisions") or []:
        image_id = int(item["image_id"])
        agent_decision = str(item.get("decision") or "uncertain")
        confidence = float(item.get("confidence") or 0.0)
        reason = str(item.get("reason") or "")[:4000]
        alts = [int(a) for a in (item.get("better_alternatives") or [])]
        risk_flags = [str(r) for r in (item.get("risk_flags") or [])]
        img_overrides: list[SafetyOverride] = []
        final = agent_decision

        if agent_decision == "uncertain":
            img_overrides.append(SafetyOverride("agent_uncertain", "image", image_id=image_id))
            final = "uncertain"

        if confidence < cfg.min_agent_confidence:
            img_overrides.append(
                SafetyOverride("image_confidence_low", "image", image_id=image_id, detail=str(confidence))
            )
            if final == "remove":
                final = "uncertain"

        if cfg.local_gates.block_missing_alternatives and final == "remove" and not alts:
            img_overrides.append(SafetyOverride("missing_alternatives", "image", image_id=image_id))
            final = "keep"

        if final == "remove":
            invalid_alts = [a for a in alts if a not in picked_ids]
            if invalid_alts:
                img_overrides.append(
                    SafetyOverride("alternatives_not_picked", "image", image_id=image_id)
                )
                final = "keep"

        if final == "remove":
            unusable_alts = [
                a
                for a in alts
                if not rows_by_id.get(a, {}).get("usable", True)
            ]
            if unusable_alts:
                img_overrides.append(
                    SafetyOverride("alternative_unusable", "image", image_id=image_id)
                )
                final = "keep"
                risk_flags = list(risk_flags) + ["replacement_unreadable"]

        if cfg.local_gates.block_if_rejected_scores_higher and final == "remove":
            row = rows_by_id.get(image_id) or {}
            best_picked_general = _best_score(rows_by_id, list(picked_ids), "score_general")
            rej_general = row.get("score_general")
            margin = cfg.local_gates.score_margin
            try:
                if (
                    best_picked_general is not None
                    and rej_general is not None
                    and float(rej_general) > float(best_picked_general) + margin
                ):
                    img_overrides.append(
                        SafetyOverride("higher_general_score", "image", image_id=image_id)
                    )
                    final = "keep"
                    risk_flags = list(risk_flags) + ["higher_technical_quality"]
            except (TypeError, ValueError):
                pass
            best_picked_technical = _best_score(rows_by_id, list(picked_ids), "score_technical")
            rej_technical = row.get("score_technical")
            try:
                if (
                    best_picked_technical is not None
                    and rej_technical is not None
                    and float(rej_technical) > float(best_picked_technical) + margin
                ):
                    img_overrides.append(
                        SafetyOverride("higher_technical_score", "image", image_id=image_id)
                    )
                    final = "keep"
            except (TypeError, ValueError):
                pass

        if cfg.local_gates.block_unique_species and final == "remove":
            unique_species = [t for t in species_by_image.get(image_id, set()) if species_counts.get(t, 0) == 1]
            if unique_species:
                img_overrides.append(SafetyOverride("unique_species", "image", image_id=image_id))
                final = "keep"
                risk_flags = list(risk_flags) + ["unique_species_or_subject"]

        if cfg.local_gates.block_unique_keywords and final == "remove":
            kws = _keywords_for_row(rows_by_id.get(image_id) or {})
            unique_kws = [k for k in kws if keyword_counts.get(k, 0) == 1 and not k.lower().startswith("species:")]
            if unique_kws:
                img_overrides.append(SafetyOverride("unique_keyword", "image", image_id=image_id))
                final = "keep"

        outlier_z = rows_by_id.get(image_id, {}).get("embedding_outlier_z")
        if cfg.local_gates.block_embedding_outliers and final == "remove" and outlier_z is not None:
            try:
                if float(outlier_z) >= cfg.local_gates.outlier_z_threshold:
                    img_overrides.append(SafetyOverride("embedding_outlier", "image", image_id=image_id))
                    final = "keep"
                    risk_flags = list(risk_flags) + ["visually_unique"]
            except (TypeError, ValueError):
                pass

        if not rows_by_id.get(image_id, {}).get("usable", True) and final == "remove":
            img_overrides.append(SafetyOverride("unreadable_preview", "image", image_id=image_id))
            final = "keep"

        if group_blocked and final == "remove":
            final = "keep"
            img_overrides.append(SafetyOverride("group_blocked", "image", image_id=image_id))

        # Never upgrade keep/uncertain to remove locally
        if agent_decision != "remove" and final == "remove":
            final = agent_decision

        image_decisions.append(
            GatedImageDecision(
                image_id=image_id,
                agent_decision=agent_decision,
                final_decision=final,
                confidence=confidence,
                reason=reason,
                better_alternatives=alts,
                risk_flags=risk_flags,
                safety_overrides=img_overrides,
            )
        )
        overrides.extend(img_overrides)

    removable = [d for d in image_decisions if d.final_decision == "remove"]
    group_decision_allowed = bool(removable) and not group_blocked

    return SafetyResult(
        group_blocked=group_blocked,
        group_decision_allowed=group_decision_allowed,
        overrides=overrides,
        image_decisions=image_decisions,
    )
