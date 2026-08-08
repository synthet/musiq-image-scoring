"""Shared helpers for the student-scorer research package.

No production DB writes. Training artifacts stay under ``artifacts/student_scorer/``.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

ARTIFACTS_ROOT = PROJECT_ROOT / "artifacts" / "student_scorer"
DEFAULT_TEACHERS: tuple[str, ...] = ("spaq", "ava", "liqe", "topiq", "arniqa")
COMPOSITE_KEYS: tuple[str, ...] = ("general", "technical", "aesthetic")
PROVENANCE_HUMAN = "human"
PROVENANCE_AUTOMATIC = "automatic"
PROVENANCE_UNKNOWN = "unknown"
PROTOCOL_ID_PREFIX = "student_scorer_protocol"

# Initial gates (study defaults). Phase 0 may revise; freeze into evaluation_protocol.json.
DEFAULT_GATES: dict[str, Any] = {
    "composite_spearman_min": 0.95,
    "median_teacher_spearman_min": 0.90,
    "composite_mae_max": 0.03,
    "confident_pair_agreement_min": 0.95,
    "subgroup_spearman_drop_max": 0.05,
    "speedup_vs_ensemble_min": 3.0,
    "pair_margin": 0.04,
    "saturation_low": 0.02,
    "saturation_high": 0.98,
    "bootstrap_reps": 200,
    "bootstrap_seed": 42,
    "bootstrap_confidence": 0.95,
    "human_noninferiority_margin": 0.02,
    "min_subgroup_n": 30,
    "split_seed": 42,
    "train_frac": 0.75,
    "val_frac": 0.125,
    "test_frac": 0.125,
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def canonical_json(obj: Any) -> str:
    """Stable JSON for hashing (sorted keys, compact separators)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def stable_hash(obj: Any) -> str:
    return sha256_text(canonical_json(obj))


def set_seed(seed: int) -> None:
    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed)
    except ImportError:
        pass
    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except ImportError:
        pass


def redact_paths(obj: Any) -> Any:
    """Strip absolute Windows/Unix home paths from nested structures for protocol docs."""
    if isinstance(obj, dict):
        return {k: redact_paths(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_paths(v) for v in obj]
    if isinstance(obj, str):
        s = obj
        s = re.sub(r"[A-Za-z]:\\\\Users\\\\[^\\\\/]+", "<USER>", s)
        s = re.sub(r"[A-Za-z]:/Users/[^/]+", "<USER>", s)
        s = re.sub(r"/home/[^/]+", "<USER>", s)
        s = re.sub(r"C:\\\\Users\\\\[^\\\\]+", "<USER>", s)
        return s
    return obj


def preprocessing_fingerprint(
    *,
    musiq_version: str,
    method: str,
    max_resolution: int,
    jpeg_quality: int,
    preprocess_source_hash: str,
) -> dict[str, Any]:
    payload = {
        "musiq_version": musiq_version,
        "raw_conversion_method": method,
        "max_resolution": int(max_resolution),
        "jpeg_quality": int(jpeg_quality),
        "preprocess_source_hash": preprocess_source_hash,
        "pad": "black_square",
        "resize": "bicubic_thumbnail_fit",
    }
    payload["fingerprint"] = stable_hash(payload)
    return payload


def hash_preprocess_source() -> str:
    """Hash the production preprocess_image implementation for P0 fingerprinting."""
    path = PROJECT_ROOT / "scripts" / "python" / "run_all_musiq_models.py"
    if not path.is_file():
        return "missing"
    text = path.read_text(encoding="utf-8", errors="replace")
    # Bound the hash to the preprocess_image method body when present.
    start = text.find("def preprocess_image")
    end = text.find("\n    def ", start + 1) if start >= 0 else -1
    chunk = text[start:end] if start >= 0 and end > start else text
    return sha256_text(chunk)


def freeze_scoring_contract(
    fusion: Mapping[str, Mapping[str, float]] | None = None,
    anchors: Mapping[str, Mapping[str, float]] | None = None,
    models_cfg: Mapping[str, Mapping[str, Any]] | None = None,
    *,
    musiq_version: str | None = None,
    raw_method: str = "rawpy_half",
    max_resolution: int = 512,
    jpeg_quality: int = 85,
) -> dict[str, Any]:
    """Build a redacted protocol snapshot of the live scoring contract (no secrets)."""
    from modules.score_normalization import (
        DEFAULT_COMPOSITE_WEIGHTS,
        DEFAULT_PERCENTILE_ANCHORS,
    )

    fusion_out = dict(fusion) if fusion else dict(DEFAULT_COMPOSITE_WEIGHTS)
    anchors_out = dict(anchors) if anchors else dict(DEFAULT_PERCENTILE_ANCHORS)
    models_out = dict(models_cfg) if models_cfg else {}

    teachers = sorted(
        {
            name
            for cat in fusion_out.values()
            for name in (cat or {}).keys()
        }
    )
    if not teachers:
        teachers = list(DEFAULT_TEACHERS)

    if musiq_version is None:
        try:
            from scripts.python.run_all_musiq_models import MultiModelMUSIQ

            musiq_version = MultiModelMUSIQ.VERSION
        except Exception:
            musiq_version = "unknown"

    prep = preprocessing_fingerprint(
        musiq_version=str(musiq_version),
        method=raw_method,
        max_resolution=max_resolution,
        jpeg_quality=jpeg_quality,
        preprocess_source_hash=hash_preprocess_source(),
    )

    contract = {
        "teachers": teachers,
        "fusion": fusion_out,
        "percentile_anchors": anchors_out,
        "scoring_models": models_out,
        "preprocessing": prep,
        "composite_rounding_decimals": 4,
        "ims_primary_key": ["image_id", "model_name"],
    }
    contract["contract_hash"] = stable_hash(
        {k: contract[k] for k in ("teachers", "fusion", "percentile_anchors", "preprocessing")}
    )
    return redact_paths(contract)


def compute_composites_frozen(
    scores: Mapping[str, float],
    *,
    fusion: Mapping[str, Mapping[str, float]],
    anchors: Mapping[str, Mapping[str, float]],
    decimals: int = 4,
) -> dict[str, float]:
    """Replay composites with frozen anchors/weights (no live config load)."""
    from modules.score_normalization import rescale_percentile

    rescaled: dict[str, float] = {}
    for model, score in scores.items():
        if model in anchors:
            a = anchors[model]
            rescaled[model] = rescale_percentile(float(score), float(a["p02"]), float(a["p98"]))
        else:
            rescaled[model] = float(score)

    out: dict[str, float] = {}
    for category in COMPOSITE_KEYS:
        cat_weights = fusion.get(category, {}) or {}
        active = {m: w for m, w in cat_weights.items() if m in rescaled}
        if not active:
            out[category] = 0.0
            continue
        total_weight = sum(active.values())
        total = sum(w * rescaled[m] for m, w in active.items())
        val = total / total_weight if total_weight > 0 else 0.0
        out[category] = round(max(0.0, min(1.0, val)), decimals)
    return out


def classify_label_provenance(
    *,
    rating: Any = None,
    pick_status: Any = None,
    cull_decision: Any = None,
    rating_source: str | None = None,
    pick_source: str | None = None,
    cull_source: str | None = None,
) -> dict[str, str]:
    """Map candidate supervision fields to human / automatic / unknown.

    Without an independently verifiable source field, treat as unknown — never
    promote automatic pipeline ratings to human metrics.
    """
    human_tokens = {"human", "user", "manual", "xmp_user", "lightroom_user"}
    auto_tokens = {"automatic", "auto", "pipeline", "model", "ensemble", "system"}

    def _one(value: Any, source: str | None) -> str:
        if value is None or value == "" or value == 0:
            return PROVENANCE_UNKNOWN
        src = (source or "").strip().lower()
        if src in human_tokens:
            return PROVENANCE_HUMAN
        if src in auto_tokens or src.startswith("auto"):
            return PROVENANCE_AUTOMATIC
        # Present value but no proven source → unknown (exclude from human loss).
        return PROVENANCE_UNKNOWN

    return {
        "rating": _one(rating, rating_source),
        "pick_status": _one(pick_status, pick_source),
        "cull_decision": _one(cull_decision, cull_source),
    }


def is_human_supervision(provenance: Mapping[str, str], field: str) -> bool:
    return provenance.get(field) == PROVENANCE_HUMAN


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_artifacts_dir(run_id: str | None = None) -> Path:
    root = ARTIFACTS_ROOT if not run_id else ARTIFACTS_ROOT / run_id
    root.mkdir(parents=True, exist_ok=True)
    return root


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    n = len(xs)
    if n < 2 or n != len(ys):
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def _rankdata(vals: Sequence[float]) -> list[float]:
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    ranks = [0.0] * len(vals)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    return pearson(_rankdata(xs), _rankdata(ys))


def kendall_tau(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    n = len(xs)
    if n < 2 or n != len(ys):
        return None
    concordant = discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            dx = xs[i] - xs[j]
            dy = ys[i] - ys[j]
            if dx == 0 or dy == 0:
                continue
            if dx * dy > 0:
                concordant += 1
            else:
                discordant += 1
    total = concordant + discordant
    if total == 0:
        return None
    return (concordant - discordant) / total


def mae(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if not xs or len(xs) != len(ys):
        return None
    return sum(abs(a - b) for a, b in zip(xs, ys)) / len(xs)


def rmse(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if not xs or len(xs) != len(ys):
        return None
    return (sum((a - b) ** 2 for a, b in zip(xs, ys)) / len(xs)) ** 0.5


def regression_metrics(pred: Sequence[float], target: Sequence[float]) -> dict[str, float | None]:
    return {
        "n": len(pred),
        "mae": mae(pred, target),
        "rmse": rmse(pred, target),
        "pearson": pearson(pred, target),
        "spearman": spearman(pred, target),
        "kendall": kendall_tau(pred, target),
    }


def saturated_mask(
    values: Sequence[float],
    *,
    low: float = 0.02,
    high: float = 0.98,
) -> list[bool]:
    return [low < float(v) < high for v in values]


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}
