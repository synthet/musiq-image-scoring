"""Stack-relative culling utility metrics and group-aware bootstrap."""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Any, Mapping, Sequence

from scripts.research.student_scorer.common import DEFAULT_GATES
from scripts.research.student_scorer.objectives import pair_is_confident


def stack_unit(row: Mapping[str, Any]) -> str:
    """Prefer sub_stack_id; fall back to stack_id, burst_uuid, then image singleton."""
    if row.get("sub_stack_id") is not None:
        return f"sub:{row['sub_stack_id']}"
    if row.get("stack_id") is not None:
        return f"stack:{row['stack_id']}"
    if row.get("burst_uuid"):
        return f"burst:{row['burst_uuid']}"
    return f"img:{row['image_id']}"


def pairwise_accuracy(
    rows: Sequence[Mapping[str, Any]],
    pred_key: str,
    target_key: str,
    *,
    margin: float = 0.04,
) -> dict[str, Any]:
    """Within-stack pairwise agreement on confident target pairs."""
    by_stack: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for r in rows:
        by_stack[stack_unit(r)].append(r)

    agree = total = 0
    for members in by_stack.values():
        if len(members) < 2:
            continue
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                ta, tb = a.get(target_key), b.get(target_key)
                pa, pb = a.get(pred_key), b.get(pred_key)
                if None in (ta, tb, pa, pb):
                    continue
                if not pair_is_confident(float(ta), float(tb), margin):
                    continue
                total += 1
                truth_prefer_a = float(ta) > float(tb)
                pred_prefer_a = float(pa) > float(pb)
                if truth_prefer_a == pred_prefer_a:
                    agree += 1
    return {
        "n_pairs": total,
        "accuracy": (agree / total) if total else None,
        "margin": margin,
    }


def topk_agreement(
    rows: Sequence[Mapping[str, Any]],
    pred_key: str,
    target_key: str,
    *,
    k: int = 1,
) -> dict[str, Any]:
    by_stack: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for r in rows:
        by_stack[stack_unit(r)].append(r)
    hits = n = 0
    for members in by_stack.values():
        if len(members) < 2:
            continue
        n += 1
        ranked_t = sorted(members, key=lambda r: float(r.get(target_key) or 0), reverse=True)
        ranked_p = sorted(members, key=lambda r: float(r.get(pred_key) or 0), reverse=True)
        kk = min(k, len(members))
        top_t = {r["image_id"] for r in ranked_t[:kk]}
        top_p = {r["image_id"] for r in ranked_p[:kk]}
        if top_t & top_p:
            hits += 1
    return {"n_stacks": n, f"top{k}_hit_rate": (hits / n) if n else None}


def ndcg_at_k(
    rows: Sequence[Mapping[str, Any]],
    pred_key: str,
    target_key: str,
    *,
    k: int = 3,
) -> dict[str, Any]:
    import math

    by_stack: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for r in rows:
        by_stack[stack_unit(r)].append(r)

    def dcg(rels: list[float]) -> float:
        return sum((2**r - 1) / math.log2(i + 2) for i, r in enumerate(rels))

    scores = []
    for members in by_stack.values():
        if len(members) < 2:
            continue
        kk = min(k, len(members))
        ideal = sorted((float(r.get(target_key) or 0) for r in members), reverse=True)[:kk]
        ranked = sorted(members, key=lambda r: float(r.get(pred_key) or 0), reverse=True)[:kk]
        rels = [float(r.get(target_key) or 0) for r in ranked]
        idcg = dcg(ideal)
        if idcg <= 0:
            continue
        scores.append(dcg(rels) / idcg)
    return {"n_stacks": len(scores), f"ndcg@{k}": (sum(scores) / len(scores)) if scores else None}


def group_bootstrap(
    rows: Sequence[Mapping[str, Any]],
    metric_fn,
    *,
    reps: int = 200,
    seed: int = 42,
    confidence: float = 0.95,
) -> dict[str, Any]:
    """Bootstrap by stack unit so members stay together (AC-6)."""
    by_stack: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for r in rows:
        by_stack[stack_unit(r)].append(r)
    keys = list(by_stack.keys())
    if not keys:
        return {"mean": None, "low": None, "high": None, "reps": 0}

    rng = random.Random(seed)
    samples = []
    for _ in range(reps):
        drawn_keys = [rng.choice(keys) for _ in keys]
        drawn_rows = [r for k in drawn_keys for r in by_stack[k]]
        val = metric_fn(drawn_rows)
        if isinstance(val, dict):
            # take first numeric
            val = next((v for v in val.values() if isinstance(v, (int, float))), None)
        if val is not None:
            samples.append(float(val))
    if not samples:
        return {"mean": None, "low": None, "high": None, "reps": 0}
    samples.sort()
    alpha = 1.0 - confidence
    lo_i = int(alpha / 2 * (len(samples) - 1))
    hi_i = int((1 - alpha / 2) * (len(samples) - 1))
    return {
        "mean": sum(samples) / len(samples),
        "low": samples[lo_i],
        "high": samples[hi_i],
        "reps": len(samples),
    }


def culling_report(
    rows: Sequence[Mapping[str, Any]],
    pred_key: str = "pred_general",
    target_key: str = "score_general",
    *,
    gates: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    g = {**DEFAULT_GATES, **(gates or {})}
    margin = float(g["pair_margin"])
    pair = pairwise_accuracy(rows, pred_key, target_key, margin=margin)
    top1 = topk_agreement(rows, pred_key, target_key, k=1)
    top3 = topk_agreement(rows, pred_key, target_key, k=3)
    ndcg = ndcg_at_k(rows, pred_key, target_key, k=3)
    pair_pass = (
        pair["accuracy"] is not None and pair["accuracy"] >= g["confident_pair_agreement_min"]
    )
    return {
        "pairwise": pair,
        "top1": top1,
        "top3": top3,
        "ndcg": ndcg,
        "gates": {
            "confident_pair_agreement": {
                "value": pair["accuracy"],
                "threshold": g["confident_pair_agreement_min"],
                "pass": pair_pass,
            }
        },
    }
