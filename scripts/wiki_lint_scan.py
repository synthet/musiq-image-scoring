#!/usr/bin/env python3
"""Read-only wiki lint: orphans, broken internal links, missing index targets."""
from __future__ import annotations

import re
import sys
from pathlib import Path

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
HUB_NAMES = ("INDEX.md", "README.md")
SKIP_PREFIXES = ("http", "#", "mailto:", "file:")


def resolve_link(from_file: Path, target: str, docs_root: Path) -> str | None:
    t = target.strip()
    if not t or any(t.startswith(p) for p in SKIP_PREFIXES):
        return None
    t = t.split("#")[0]
    if not t or t.endswith("/"):
        return None
    resolved = (from_file.parent / t).resolve()
    try:
        return resolved.relative_to(docs_root.resolve()).as_posix()
    except ValueError:
        return None


def lint_docs(docs_root: Path) -> dict:
    docs_root = docs_root.resolve()
    all_md = {p.relative_to(docs_root).as_posix() for p in docs_root.rglob("*.md")}
    hubs = [p for p in docs_root.rglob("*.md") if p.name in HUB_NAMES]

    indexed: set[str] = set()
    for hub in hubs:
        text = hub.read_text(encoding="utf-8", errors="replace")
        for m in LINK_RE.finditer(text):
            rel = resolve_link(hub, m.group(1), docs_root)
            if rel:
                indexed.add(rel)

    broken_docs: list[tuple[str, str]] = []
    broken_code: list[tuple[str, str]] = []
    inbound: dict[str, set[str]] = {p: set() for p in all_md}

    for md in sorted(all_md):
        p = docs_root / md
        text = p.read_text(encoding="utf-8", errors="replace")
        for m in LINK_RE.finditer(text):
            raw = m.group(1).strip()
            rel = resolve_link(p, raw, docs_root)
            if rel is None:
                continue
            if rel in all_md and rel != md:
                inbound[rel].add(md)
            target = docs_root / rel
            if target.exists():
                continue
            if raw.startswith("../") and "modules/" in raw:
                broken_code.append((md, raw))
            elif "/" not in raw and raw.endswith(".md"):
                broken_docs.append((md, raw))
            elif rel.startswith("archive/") or "planning/" in rel:
                broken_docs.append((md, raw))
            else:
                broken_docs.append((md, raw))

    meta = {"log.md", "WIKI_SCHEMA.md", "CANONICAL_SOURCES.md"}
    orphans = sorted(x for x in all_md - indexed if x not in meta)
    missing = sorted(x for x in indexed if not (docs_root / x).exists())
    isolated = sorted(p for p in all_md if not inbound[p] and p not in meta)

    def classify(path: str) -> str:
        if path.startswith("archive/"):
            return "archive"
        if path.startswith("reviews/"):
            return "reviews"
        if "/INDEX.md" in path or path.endswith("/README.md"):
            return "meta"
        return "active"

    orphan_by_class = {}
    for o in orphans:
        orphan_by_class.setdefault(classify(o), []).append(o)

    return {
        "total": len(all_md),
        "hubs": len(hubs),
        "indexed_refs": len(indexed),
        "orphans": orphans,
        "orphan_by_class": orphan_by_class,
        "missing": missing,
        "broken_docs": broken_docs,
        "broken_code": broken_code,
        "isolated_active": [p for p in isolated if classify(p) == "active"],
    }


def main() -> int:
    roots = sys.argv[1:] or [
        Path(__file__).resolve().parents[1] / "docs",
    ]
    for root in roots:
        root = Path(root)
        r = lint_docs(root)
        print(f"=== {root} ===")
        print(
            f"md={r['total']} hubs={r['hubs']} indexed_refs={r['indexed_refs']} "
            f"orphans={len(r['orphans'])} missing={len(r['missing'])} "
            f"broken_docs={len(r['broken_docs'])} broken_code={len(r['broken_code'])}"
        )
        for cls, items in sorted(r["orphan_by_class"].items()):
            print(f"  orphans[{cls}]: {len(items)}")
        if r["missing"]:
            print("MISSING:")
            for m in r["missing"]:
                print(f"  {m}")
        if r["isolated_active"]:
            print("ISOLATED_ACTIVE (no inbound):")
            for i in r["isolated_active"][:25]:
                print(f"  {i}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
