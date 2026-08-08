"""Manifest rows, target masks, and offline dataset helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

from scripts.research.student_scorer.common import (
    DEFAULT_TEACHERS,
    classify_label_provenance,
    compute_composites_frozen,
    stable_hash,
)


@dataclass
class ManifestRow:
    image_id: int
    path_token: str
    image_hash: str | None = None
    hash_version: str | None = None
    burst_uuid: str | None = None
    stack_id: int | None = None
    sub_stack_id: int | None = None
    folder_id: int | None = None
    capture_day: str | None = None
    file_exists: bool = True
    score_general: float | None = None
    score_technical: float | None = None
    score_aesthetic: float | None = None
    rating: int | None = None
    pick_status: int = 0
    cull_decision: str | None = None
    rating_source: str | None = None
    pick_source: str | None = None
    cull_source: str | None = None
    teacher_raw: dict[str, float] = field(default_factory=dict)
    teacher_normalized: dict[str, float] = field(default_factory=dict)
    teacher_versions: dict[str, str] = field(default_factory=dict)
    teacher_mask: dict[str, bool] = field(default_factory=dict)
    provenance: dict[str, str] = field(default_factory=dict)
    bird_bbox: dict[str, Any] | None = None
    embeddings_ref: dict[str, str] = field(default_factory=dict)

    def finalize_provenance(self) -> None:
        self.provenance = classify_label_provenance(
            rating=self.rating,
            pick_status=self.pick_status,
            cull_decision=self.cull_decision,
            rating_source=self.rating_source,
            pick_source=self.pick_source,
            cull_source=self.cull_source,
        )

    def to_dict(self) -> dict[str, Any]:
        self.finalize_provenance()
        return asdict(self)


def build_teacher_mask(
    teacher_normalized: Mapping[str, float | None],
    teachers: Sequence[str] = DEFAULT_TEACHERS,
) -> dict[str, bool]:
    return {
        t: teacher_normalized.get(t) is not None and teacher_normalized.get(t) == teacher_normalized.get(t)
        for t in teachers
    }


def row_content_fingerprint(rows: Sequence[Mapping[str, Any]]) -> str:
    """Order-stable hash of row content (sorted by image_id)."""
    sorted_rows = sorted(rows, key=lambda r: int(r["image_id"]))
    # Drop volatile local-only keys if present
    cleaned = []
    for r in sorted_rows:
        item = {k: r[k] for k in sorted(r.keys()) if k not in {"absolute_path", "local_path"}}
        cleaned.append(item)
    return stable_hash(cleaned)


def compute_manifest_id(
    *,
    meta: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
) -> str:
    payload = {
        "contract_hash": meta.get("contract_hash"),
        "protocol_id": meta.get("protocol_id"),
        "teachers": meta.get("teachers"),
        "preprocessing_fingerprint": (meta.get("preprocessing") or {}).get("fingerprint"),
        "row_fingerprint": row_content_fingerprint(rows),
        "n_rows": len(rows),
    }
    return "msm_" + stable_hash(payload)[:16]


def validate_manifest_against_protocol(
    meta: Mapping[str, Any],
    *,
    expected_checksum: str | None = None,
    expected_protocol_id: str | None = None,
    expected_contract_hash: str | None = None,
) -> None:
    """Raise ValueError if checksum / protocol / contract do not match."""
    if expected_protocol_id is not None and meta.get("protocol_id") != expected_protocol_id:
        raise ValueError(
            f"protocol_id mismatch: manifest={meta.get('protocol_id')!r} "
            f"expected={expected_protocol_id!r}"
        )
    if expected_contract_hash is not None and meta.get("contract_hash") != expected_contract_hash:
        raise ValueError("contract_hash mismatch — refuse to train on drifted scoring contract")
    if expected_checksum is not None and meta.get("checksum") != expected_checksum:
        raise ValueError("manifest checksum mismatch — refuse to train on mutated snapshot")


def replay_composites_for_row(
    row: Mapping[str, Any],
    *,
    fusion: Mapping[str, Mapping[str, float]],
    anchors: Mapping[str, Mapping[str, float]],
) -> dict[str, float]:
    scores = {
        k: float(v)
        for k, v in (row.get("teacher_normalized") or {}).items()
        if v is not None
    }
    return compute_composites_frozen(scores, fusion=fusion, anchors=anchors)


def b0_parity_report(
    rows: Sequence[Mapping[str, Any]],
    *,
    fusion: Mapping[str, Mapping[str, float]],
    anchors: Mapping[str, Mapping[str, float]],
    teachers: Sequence[str],
    atol: float = 5e-4,
) -> dict[str, Any]:
    """Compare stored composites vs frozen replay; separate full vs partial teacher rows."""
    full_ok = full_bad = partial_ok = partial_bad = 0
    exceptions: list[dict[str, Any]] = []
    for row in rows:
        mask = row.get("teacher_mask") or {}
        present = [t for t in teachers if mask.get(t)]
        is_full = len(present) == len(teachers)
        derived = replay_composites_for_row(row, fusion=fusion, anchors=anchors)
        stored = {
            "general": row.get("score_general"),
            "technical": row.get("score_technical"),
            "aesthetic": row.get("score_aesthetic"),
        }
        if any(stored[k] is None for k in stored):
            continue
        diffs = {k: abs(float(derived[k]) - float(stored[k])) for k in stored}
        ok = all(d <= atol for d in diffs.values())
        if is_full:
            full_ok += int(ok)
            full_bad += int(not ok)
        else:
            partial_ok += int(ok)
            partial_bad += int(not ok)
        if not ok and len(exceptions) < 50:
            exceptions.append(
                {
                    "image_id": row.get("image_id"),
                    "full_teachers": is_full,
                    "diffs": diffs,
                    "derived": derived,
                    "stored": stored,
                }
            )
    return {
        "atol": atol,
        "full_target": {"ok": full_ok, "mismatch": full_bad},
        "partial_target": {"ok": partial_ok, "mismatch": partial_bad},
        "exceptions": exceptions,
        "pass": full_bad == 0,
    }
