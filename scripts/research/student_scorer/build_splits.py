"""Connected-component splits with temporal OOD holdout and near-dupe QA."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from scripts.research.student_scorer.common import set_seed, stable_hash


@dataclass
class SplitAssignment:
    image_id: int
    component_id: str
    split: str  # train | val | test | ood_test


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def add(self, x: str) -> None:
        self.parent.setdefault(x, x)

    def find(self, x: str) -> str:
        self.add(x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _node_id(image_id: int) -> str:
    return f"img:{image_id}"


def build_components(rows: Sequence[Mapping[str, Any]]) -> dict[int, str]:
    """Union duplicates + burst/stack/sub_stack; return image_id -> component_id."""
    uf = UnionFind()
    key_members: dict[str, list[str]] = defaultdict(list)

    for row in rows:
        iid = int(row["image_id"])
        nid = _node_id(iid)
        uf.add(nid)
        h = row.get("image_hash")
        hv = row.get("hash_version") or "v0"
        if h:
            key_members[f"hash:{h}:{hv}"].append(nid)
        burst = row.get("burst_uuid")
        if burst:
            key_members[f"burst:{burst}"].append(nid)
        stack = row.get("stack_id")
        if stack is not None:
            key_members[f"stack:{stack}"].append(nid)
        sub = row.get("sub_stack_id")
        if sub is not None:
            key_members[f"sub:{sub}"].append(nid)
        # Session fallback for ungrouped later — also soft-link by folder+day when present
        folder = row.get("folder_id")
        day = row.get("capture_day")
        if folder is not None and day:
            key_members[f"session:{folder}:{day}"].append(nid)

    for members in key_members.values():
        if len(members) < 2:
            continue
        head = members[0]
        for m in members[1:]:
            uf.union(head, m)

    # Component ids from roots
    roots: dict[str, str] = {}
    out: dict[int, str] = {}
    for row in rows:
        iid = int(row["image_id"])
        root = uf.find(_node_id(iid))
        if root not in roots:
            roots[root] = f"c_{stable_hash(root)[:12]}"
        out[iid] = roots[root]
    return out


def _component_capture_day(rows: Sequence[Mapping[str, Any]], members: Sequence[int]) -> str:
    days = []
    by_id = {int(r["image_id"]): r for r in rows}
    for iid in members:
        d = by_id[iid].get("capture_day")
        if d:
            days.append(str(d))
    return max(days) if days else ""


def assign_splits(
    rows: Sequence[Mapping[str, Any]],
    *,
    seed: int = 42,
    train_frac: float = 0.75,
    val_frac: float = 0.125,
    ood_newest_fraction: float = 0.10,
) -> list[SplitAssignment]:
    """Deterministic connected-component split with temporal OOD carve-out first."""
    set_seed(seed)
    components = build_components(rows)
    members: dict[str, list[int]] = defaultdict(list)
    for iid, cid in components.items():
        members[cid].append(iid)

    # Temporal OOD: newest complete session components
    scored = [
        (cid, _component_capture_day(rows, mems), len(mems))
        for cid, mems in members.items()
    ]
    scored.sort(key=lambda t: (t[1], t[0]), reverse=True)
    n_ood = max(1, int(round(len(scored) * ood_newest_fraction))) if scored else 0
    # Only carve OOD if capture_day coverage exists
    has_days = any(d for _, d, _ in scored)
    ood_ids: set[str] = set()
    if has_days and n_ood > 0:
        for cid, day, _ in scored[:n_ood]:
            if day:
                ood_ids.add(cid)

    remaining = [cid for cid, _, _ in scored if cid not in ood_ids]
    # Deterministic shuffle by hashing component id with seed
    remaining.sort(key=lambda cid: stable_hash({"seed": seed, "cid": cid}))

    n = len(remaining)
    n_train = int(round(n * train_frac))
    n_val = int(round(n * val_frac))
    train_set = set(remaining[:n_train])
    val_set = set(remaining[n_train : n_train + n_val])
    test_set = set(remaining[n_train + n_val :])

    assignments: list[SplitAssignment] = []
    for cid, mems in members.items():
        if cid in ood_ids:
            split = "ood_test"
        elif cid in train_set:
            split = "train"
        elif cid in val_set:
            split = "val"
        elif cid in test_set:
            split = "test"
        else:
            split = "train"
        for iid in mems:
            assignments.append(SplitAssignment(iid, cid, split))
    assignments.sort(key=lambda a: a.image_id)
    return assignments


def assert_no_cross_split_groups(assignments: Sequence[SplitAssignment]) -> None:
    by_c: dict[str, set[str]] = defaultdict(set)
    for a in assignments:
        by_c[a.component_id].add(a.split)
    bad = {c: s for c, s in by_c.items() if len(s) > 1}
    if bad:
        raise AssertionError(f"components cross splits: {list(bad.items())[:5]}")


def near_duplicate_leakage(
    rows: Sequence[Mapping[str, Any]],
    assignments: Sequence[SplitAssignment],
    *,
    embedding_key: str = "embed_sim_cluster",
) -> list[dict[str, Any]]:
    """If rows carry a near-dupe cluster id, report clusters that span splits."""
    split_of = {a.image_id: a.split for a in assignments}
    clusters: dict[str, set[str]] = defaultdict(set)
    members: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        cid = row.get(embedding_key)
        if not cid:
            continue
        iid = int(row["image_id"])
        clusters[str(cid)].add(split_of[iid])
        members[str(cid)].append(iid)
    leaks = []
    for cid, splits in clusters.items():
        if len(splits) > 1:
            leaks.append({"cluster": cid, "splits": sorted(splits), "image_ids": members[cid]})
    return leaks


def merge_components_for_leaks(
    assignments: Sequence[SplitAssignment],
    leaks: Sequence[Mapping[str, Any]],
) -> list[SplitAssignment]:
    """Force leaked near-dupe clusters into one component; caller must re-assign splits."""
    # Represented as forcing same component_id string across leaked image ids —
    # rebuild mapping then caller re-runs assign_splits on rewritten rows.
    uf = UnionFind()
    id_to_comp = {a.image_id: a.component_id for a in assignments}
    for a in assignments:
        uf.add(a.component_id)
    for leak in leaks:
        ids = list(leak.get("image_ids") or [])
        if len(ids) < 2:
            continue
        head = id_to_comp[int(ids[0])]
        for iid in ids[1:]:
            uf.union(head, id_to_comp[int(iid)])
    out = []
    for a in assignments:
        root = uf.find(a.component_id)
        out.append(SplitAssignment(a.image_id, f"merged_{stable_hash(root)[:12]}", a.split))
    return out


def splits_to_dict(assignments: Sequence[SplitAssignment]) -> list[dict[str, Any]]:
    return [
        {"image_id": a.image_id, "component_id": a.component_id, "split": a.split}
        for a in assignments
    ]
