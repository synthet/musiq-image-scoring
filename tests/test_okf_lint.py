"""Tests for OKF bundle lint tooling."""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from okf_bundle import OKFDocument, expected_resource_paths, resolve_internal_link  # noqa: E402
from okf_lint import lint_bundle  # noqa: E402


def _write_concept(root: Path, rel: str, body: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


GOOD_FRONTMATTER = """---
type: Technical Reference
title: Example
description: One sentence summary.
resource: guides/example.md
tags: [docs, backend]
timestamp: 2026-06-16T00:00:00Z
okf_version: 0.1
---

# Example
"""


def test_valid_concept_passes_vexlum(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    _write_concept(root, "guides/example.md", GOOD_FRONTMATTER)

    report = lint_bundle(root, profile="vexlum", exclude_prefixes=())
    assert report.counts()["error"] == 0
    assert report.counts()["warning"] == 0


def test_missing_type_fails_minimal(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    _write_concept(
        root,
        "guides/bad.md",
        """---
title: Bad
---

# Bad
""",
    )

    report = lint_bundle(root, profile="minimal", exclude_prefixes=())
    codes = [f.code for f in report.findings]
    assert "missing_type" in codes


def test_resource_mismatch_detected(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    body = GOOD_FRONTMATTER.replace("resource: guides/example.md", "resource: wrong/path.md")
    _write_concept(root, "guides/example.md", body)

    report = lint_bundle(root, profile="vexlum", exclude_prefixes=())
    assert any(f.code == "resource_mismatch" for f in report.findings)


def test_gallery_resource_path_accepted(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    body = GOOD_FRONTMATTER.replace(
        "resource: guides/example.md",
        "resource: docs/guides/example.md",
    )
    _write_concept(root, "guides/example.md", body)

    report = lint_bundle(root, profile="vexlum", bundle_name="docs", exclude_prefixes=())
    assert not any(f.code == "resource_mismatch" for f in report.findings)


def test_log_md_exempt_from_frontmatter(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    (root / "log.md").write_text("# Wiki Log\n\nNo frontmatter here.\n", encoding="utf-8")

    report = lint_bundle(root, profile="vexlum", exclude_prefixes=())
    assert report.skipped == 1
    assert report.concepts_checked == 0
    assert report.findings == []


def test_archive_prefix_excluded(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    _write_concept(root, "archive/old.md", "# Old\n\nNo metadata.\n")

    report = lint_bundle(root, profile="vexlum", exclude_prefixes=("archive/",))
    assert report.skipped == 1
    assert not report.findings


def test_bundle_relative_link_resolves(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    _write_concept(root, "technical/FOO.md", GOOD_FRONTMATTER)
    body = GOOD_FRONTMATTER.replace("guides/example.md", "/technical/FOO.md")
    _write_concept(root, "guides/example.md", body)

    report = lint_bundle(root, profile="vexlum", exclude_prefixes=())
    assert not any(f.code == "broken_internal_link" for f in report.findings)


def test_broken_internal_link_reported(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    body = GOOD_FRONTMATTER + "\nSee [missing](/missing/page.md).\n"
    _write_concept(root, "guides/example.md", body)

    report = lint_bundle(root, profile="vexlum", exclude_prefixes=())
    assert any(f.code == "broken_internal_link" for f in report.findings)


def test_okf_document_parse_roundtrip() -> None:
    doc = OKFDocument.parse(GOOD_FRONTMATTER)
    assert doc.has_frontmatter
    assert doc.frontmatter["type"] == "Technical Reference"
    assert doc.body.startswith("# Example")


def test_expected_resource_paths_both_styles() -> None:
    paths = expected_resource_paths("guides/example.md", "docs")
    assert "guides/example.md" in paths
    assert "docs/guides/example.md" in paths


def test_only_paths_limits_scan(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    _write_concept(root, "guides/good.md", GOOD_FRONTMATTER)
    _write_concept(root, "guides/bad.md", "# Bad\n\nNo frontmatter.\n")

    report = lint_bundle(
        root,
        profile="vexlum",
        exclude_prefixes=(),
        only_paths=frozenset({"guides/good.md"}),
    )
    assert report.concepts_checked == 1
    assert report.counts()["error"] == 0


def test_resolve_internal_link_bundle_absolute(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    from_file = root / "guides" / "example.md"
    from_file.parent.mkdir(parents=True)
    from_file.touch()
    target = root / "technical" / "FOO.md"
    target.parent.mkdir(parents=True)
    target.touch()

    resolved = resolve_internal_link(from_file, "/technical/FOO.md", root)
    assert resolved == "technical/FOO.md"
