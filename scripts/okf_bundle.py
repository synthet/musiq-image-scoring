"""Shared OKF bundle parsing and link resolution for docs/ lint tools."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
SKIP_PREFIXES = ("http://", "https://", "#", "mailto:", "file:")
FRONTMATTER_DELIM = "---"
LOG_FILENAME = "log.md"
VEXLUM_PROFILE_FIELDS = ("type", "title", "description", "resource", "tags", "timestamp")


class OKFDocumentError(ValueError):
    pass


@dataclass
class OKFDocument:
    frontmatter: dict[str, Any] = field(default_factory=dict)
    body: str = ""
    has_frontmatter: bool = False

    @classmethod
    def parse(cls, text: str) -> OKFDocument:
        lines = text.splitlines()
        if not lines or lines[0].strip() != FRONTMATTER_DELIM:
            return cls(frontmatter={}, body=text, has_frontmatter=False)

        end_idx = None
        for i in range(1, len(lines)):
            if lines[i].strip() == FRONTMATTER_DELIM:
                end_idx = i
                break
        if end_idx is None:
            raise OKFDocumentError("Unterminated YAML frontmatter block")

        fm_text = "\n".join(lines[1:end_idx])
        try:
            fm = yaml.safe_load(fm_text) or {}
        except yaml.YAMLError as exc:
            raise OKFDocumentError(f"Invalid YAML in frontmatter: {exc}") from exc
        if not isinstance(fm, dict):
            raise OKFDocumentError("Frontmatter must be a YAML mapping")

        body = "\n".join(lines[end_idx + 1 :])
        if body.startswith("\n"):
            body = body[1:]
        return cls(frontmatter=fm, body=body, has_frontmatter=True)


def is_excluded_path(rel_path: str, exclude_prefixes: tuple[str, ...]) -> bool:
    normalized = rel_path.replace("\\", "/")
    return any(normalized.startswith(prefix) for prefix in exclude_prefixes)


def is_concept_file(rel_path: str) -> bool:
    name = Path(rel_path).name
    return name != LOG_FILENAME


def expected_resource_paths(rel_path: str, bundle_label: str = "docs") -> set[str]:
    """Accept backend-style (under docs/) and gallery-style (docs/...) resource values."""
    posix = rel_path.replace("\\", "/")
    return {posix, f"{bundle_label}/{posix}"}


def validate_timestamp(value: Any) -> str | None:
    if value is None or value == "":
        return "timestamp is missing or empty"
    if isinstance(value, datetime):
        return None
    if not isinstance(value, str):
        return "timestamp must be a string or datetime"
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        datetime.fromisoformat(raw)
    except ValueError:
        return f"timestamp is not valid ISO-8601: {value!r}"
    return None


def resolve_internal_link(from_file: Path, target: str, docs_root: Path) -> str | None:
    """Resolve a markdown link to a bundle-relative path, or None if external/skipped."""
    t = target.strip()
    if not t or any(t.startswith(p) for p in SKIP_PREFIXES):
        return None
    t = t.split("#")[0].strip()
    if not t or t.endswith("/"):
        return None

    docs_root = docs_root.resolve()
    if t.startswith("/"):
        rel = t.lstrip("/")
        candidate = (docs_root / rel).resolve()
    else:
        candidate = (from_file.parent / t).resolve()

    try:
        return candidate.relative_to(docs_root).as_posix()
    except ValueError:
        return None


def collect_markdown_links(text: str, from_file: Path, docs_root: Path) -> list[tuple[str, str | None]]:
    links: list[tuple[str, str | None]] = []
    for match in LINK_RE.finditer(text):
        raw = match.group(1).strip()
        links.append((raw, resolve_internal_link(from_file, raw, docs_root)))
    return links
