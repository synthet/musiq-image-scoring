"""Parse memory.md, merge session candidates, emit dream proposal + changelog."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from scripts.agent_memory import schema
from scripts.agent_memory.paths import load_config

_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


def normalize_text(text: str) -> str:
    return _NORMALIZE_RE.sub(" ", text.lower()).strip()


@dataclass
class MemoryItem:
    text: str
    section: str
    sources: list[str] = field(default_factory=list)
    confidence: str = "medium"

    @property
    def key(self) -> str:
        return f"{self.section}::{normalize_text(self.text)}"


def parse_memory_markdown(content: str) -> dict[str, list[MemoryItem]]:
    """Parse H2 sections into lists of MemoryItem."""
    sections: dict[str, list[MemoryItem]] = {s: [] for s in schema.SECTION_ORDER}
    current: str | None = None
    for line in content.splitlines():
        if line.startswith("## "):
            title = line[3:].strip()
            if title in sections:
                current = title
            else:
                current = None
            continue
        if current and line.startswith("- "):
            text = line[2:].strip()
            if not text or text == schema.PLACEHOLDER_NONE:
                continue
            sections[current].append(MemoryItem(text=text, section=current))
    return sections


def load_sessions(
    raw_dir: Path,
    *,
    max_sessions: int,
    max_bytes: int,
) -> list[tuple[str, dict[str, Any]]]:
    """Load recent YAML sessions newest-first."""
    files = sorted(raw_dir.glob("*.yaml"), key=lambda p: p.stat().st_mtime, reverse=True)
    loaded: list[tuple[str, dict[str, Any]]] = []
    for path in files[:max_sessions]:
        if path.stat().st_size > max_bytes:
            continue
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if isinstance(data, dict):
            loaded.append((path.name, data))
    return loaded


def _item_from_candidate(
    cand: dict[str, Any], session_name: str
) -> MemoryItem | None:
    cat = cand.get("category")
    section = schema.CATEGORY_TO_SECTION.get(cat)
    if not section:
        return None
    text = (cand.get("text") or "").strip()
    if not text:
        return None
    return MemoryItem(
        text=text,
        section=section,
        sources=[session_name],
        confidence=cand.get("confidence") or "medium",
    )


def merge_sections(
    base: dict[str, list[MemoryItem]],
    sessions: list[tuple[str, dict[str, Any]]],
    *,
    max_per_section: int,
) -> tuple[dict[str, list[MemoryItem]], dict[str, list[str]]]:
    """
    Merge session candidates into base sections.
    Returns (merged_sections, changelog_dict).
    """
    changelog: dict[str, list[str]] = {
        "added": [],
        "updated": [],
        "removed": [],
        "deprecated": [],
        "uncertain": [],
    }
    merged = {s: [MemoryItem(i.text, i.section, list(i.sources)) for i in items] for s, items in base.items()}
    index: dict[str, MemoryItem] = {}
    for section, items in merged.items():
        for item in items:
            index[item.key] = item

    open_section = "Open Questions"

    for session_name, data in sessions:
        for cand in data.get("memory_candidates") or []:
            if not isinstance(cand, dict):
                continue
            new_item = _item_from_candidate(cand, session_name)
            if not new_item:
                continue
            existing = index.get(new_item.key)
            if existing:
                for src in new_item.sources:
                    if src not in existing.sources:
                        existing.sources.append(src)
                continue
            # Contradiction: same normalized text in different section?
            cross = _find_cross_section_conflict(merged, new_item)
            if cross:
                msg = (
                    f'"{new_item.text}" conflicts with existing in "{cross.section}" '
                    f"(from: {session_name})"
                )
                changelog["uncertain"].append(msg)
                oq = MemoryItem(
                    text=f"Resolve: {new_item.text} vs {cross.text}",
                    section=open_section,
                    sources=[session_name],
                    confidence="low",
                )
                okey = oq.key
                if okey not in index:
                    merged[open_section].append(oq)
                    index[okey] = oq
                    changelog["added"].append(f"{oq.text} (from: {session_name})")
                continue
            merged[new_item.section].append(new_item)
            index[new_item.key] = new_item
            changelog["added"].append(f"{new_item.text} (from: {session_name})")

    for section in schema.SECTION_ORDER:
        items = merged[section]
        if len(items) > max_per_section:
            dropped = items[max_per_section:]
            merged[section] = items[:max_per_section]
            for d in dropped:
                changelog["removed"].append(f"{d.text} (truncated: section limit)")

    return merged, changelog


def _find_cross_section_conflict(
    merged: dict[str, list[MemoryItem]], new_item: MemoryItem
) -> MemoryItem | None:
    norm = normalize_text(new_item.text)
    for section, items in merged.items():
        if section == new_item.section:
            continue
        for item in items:
            if normalize_text(item.text) == norm:
                return item
    return None


def diff_against_base(
    base: dict[str, list[MemoryItem]],
    merged: dict[str, list[MemoryItem]],
) -> dict[str, list[str]]:
    """Compare merged to original base for updated/removed."""
    changelog: dict[str, list[str]] = {
        "added": [],
        "updated": [],
        "removed": [],
        "deprecated": [],
        "uncertain": [],
    }
    for section in schema.SECTION_ORDER:
        base_keys = {normalize_text(i.text) for i in base[section]}
        merged_keys = {normalize_text(i.text) for i in merged[section]}
        for item in merged[section]:
            n = normalize_text(item.text)
            if n not in base_keys:
                entry = item.text
                if item.sources:
                    entry += f" (from: {', '.join(item.sources)})"
                if entry not in changelog["added"]:
                    changelog["added"].append(entry)
        for item in base[section]:
            n = normalize_text(item.text)
            if n not in merged_keys:
                changelog["removed"].append(item.text)
    return changelog


def merge_changelogs(*parts: dict[str, list[str]]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {
        "added": [],
        "updated": [],
        "removed": [],
        "deprecated": [],
        "uncertain": [],
    }
    seen: dict[str, set[str]] = {k: set() for k in out}
    for part in parts:
        for key, entries in part.items():
            for e in entries:
                if e not in seen[key]:
                    seen[key].add(e)
                    out[key].append(e)
    return out


def render_memory_markdown(
    sections: dict[str, list[MemoryItem]],
    *,
    front_matter: dict[str, Any] | None = None,
) -> str:
    lines: list[str] = []
    if front_matter:
        lines.append("---")
        lines.append(yaml.safe_dump(front_matter, default_flow_style=False).strip())
        lines.append("---")
        lines.append("")
    lines.append("# Project Memory")
    lines.append("")
    lines.append("Proposed consolidated memory (review before promote).")
    lines.append("")
    for section in schema.SECTION_ORDER:
        lines.append(f"## {section}")
        lines.append("")
        items = sections[section]
        if not items:
            lines.append(f"- {schema.PLACEHOLDER_NONE}")
        else:
            for item in items:
                lines.append(f"- {item.text}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_changelog(changelog: dict[str, list[str]]) -> str:
    titles = {
        "added": "Added",
        "updated": "Updated",
        "removed": "Removed",
        "deprecated": "Deprecated",
        "uncertain": "Uncertain / needs review",
    }
    lines = ["# Dream changelog", ""]
    for key, title in titles.items():
        lines.append(f"## {title}")
        lines.append("")
        entries = changelog.get(key) or []
        if not entries:
            lines.append("- (none)")
        else:
            for e in entries:
                lines.append(f"- {e}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def run_dream(
    repo_root: Path,
    *,
    max_sessions: int | None = None,
) -> tuple[Path, Path]:
    """Generate dream + changelog paths. Never writes memory.md."""
    config = load_config(repo_root)
    dirs = {
        "raw": repo_root / ".agent-memory" / "raw-sessions",
        "dreams": repo_root / ".agent-memory" / "dreams",
        "memory": repo_root / ".agent-memory" / "memory.md",
    }
    dirs["dreams"].mkdir(parents=True, exist_ok=True)

    base_content = ""
    if dirs["memory"].is_file():
        base_content = dirs["memory"].read_text(encoding="utf-8")

    base_sections = parse_memory_markdown(base_content)
    sessions = load_sessions(
        dirs["raw"],
        max_sessions=max_sessions or config["max_sessions"],
        max_bytes=config["max_session_bytes"],
    )
    session_names = [n for n, _ in sessions]

    merged, cand_changelog = merge_sections(
        base_sections,
        sessions,
        max_per_section=config["max_items_per_section"],
    )
    struct_changelog = diff_against_base(base_sections, merged)
    changelog = merge_changelogs(cand_changelog, struct_changelog)

    from scripts.agent_memory.limits import dream_timestamp_slug

    slug = dream_timestamp_slug()
    item_counts = {s: len(merged[s]) for s in schema.SECTION_ORDER}
    front_matter = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_sessions": session_names,
        "item_counts": item_counts,
    }
    dream_path = dirs["dreams"] / f"{slug}.md"
    changelog_path = dirs["dreams"] / f"{slug}-changelog.md"
    dream_body = render_memory_markdown(merged, front_matter=front_matter)
    from scripts.agent_memory.secrets import assert_no_secrets

    assert_no_secrets(dream_body, context="dream proposal")
    assert_no_secrets(render_changelog(changelog), context="changelog")
    dream_path.write_text(dream_body, encoding="utf-8")
    changelog_path.write_text(render_changelog(changelog), encoding="utf-8")
    return dream_path, changelog_path


def extract_body_from_dream(content: str) -> str:
    """Strip YAML front matter and dream-only banners for promotion."""
    body = content
    if body.startswith("---"):
        parts = body.split("---", 2)
        if len(parts) >= 3:
            body = parts[2].lstrip("\n")
    lines = body.splitlines()
    filtered: list[str] = []
    for line in lines:
        if "Proposed consolidated memory" in line:
            continue
        filtered.append(line)
    body = "\n".join(filtered).rstrip() + "\n"
    if not body.startswith("# Project Memory"):
        body = "# Project Memory\n\n" + body.lstrip()
    return body


def promote_dream(repo_root: Path, dream_path: Path, *, force: bool = False) -> Path:
    """Promote dream to memory.md with archive."""
    memory_path = repo_root / ".agent-memory" / "memory.md"
    archive_dir = repo_root / ".agent-memory" / "dreams" / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    changelog_path = dream_path.with_name(f"{dream_path.stem}-changelog.md")
    if not changelog_path.is_file() and not force:
        raise FileNotFoundError(
            f"Changelog missing: {changelog_path}. Use --force to promote anyway."
        )

    content = dream_path.read_text(encoding="utf-8")
    from scripts.agent_memory.secrets import assert_no_secrets

    assert_no_secrets(content, context="dream promotion")
    body = extract_body_from_dream(content)

    from scripts.agent_memory.limits import dream_timestamp_slug

    if memory_path.is_file():
        archive_name = f"memory-{dream_timestamp_slug()}.md"
        archive_path = archive_dir / archive_name
        archive_path.write_text(memory_path.read_text(encoding="utf-8"), encoding="utf-8")

    memory_path.write_text(body, encoding="utf-8")
    return memory_path


def load_context(repo_root: Path) -> str:
    """Load memory.md for context printing."""
    memory_path = repo_root / ".agent-memory" / "memory.md"
    if not memory_path.is_file():
        return ""
    return memory_path.read_text(encoding="utf-8")
