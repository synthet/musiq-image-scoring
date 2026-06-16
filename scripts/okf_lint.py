#!/usr/bin/env python3
"""OKF bundle linter for docs/ trees (backend and sibling gallery)."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from okf_bundle import (  # noqa: E402
    OKFDocument,
    OKFDocumentError,
    VEXLUM_PROFILE_FIELDS,
    collect_markdown_links,
    expected_resource_paths,
    is_concept_file,
    is_excluded_path,
    validate_timestamp,
)

PROFILES = ("minimal", "vexlum")
SEVERITIES = ("error", "warning", "info")


@dataclass
class LintFinding:
    path: str
    code: str
    message: str
    severity: str = "error"


@dataclass
class BundleReport:
    bundle_root: str
    bundle_name: str
    profile: str
    total_md: int = 0
    concepts_checked: int = 0
    skipped: int = 0
    findings: list[LintFinding] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        out = {s: 0 for s in SEVERITIES}
        for f in self.findings:
            out[f.severity] = out.get(f.severity, 0) + 1
        return out


def lint_bundle(
    docs_root: Path,
    *,
    profile: str = "vexlum",
    bundle_name: str = "docs",
    exclude_prefixes: tuple[str, ...] = ("archive/",),
    only_paths: frozenset[str] | None = None,
) -> BundleReport:
    docs_root = docs_root.resolve()
    report = BundleReport(
        bundle_root=str(docs_root),
        bundle_name=bundle_name,
        profile=profile,
    )
    all_md = sorted(p.relative_to(docs_root).as_posix() for p in docs_root.rglob("*.md"))
    report.total_md = len(all_md)
    all_md_set = set(all_md)

    scan_paths = all_md
    if only_paths is not None:
        scan_paths = sorted(p for p in all_md if p in only_paths)

    for rel in scan_paths:
        if not is_concept_file(rel):
            report.skipped += 1
            continue
        if is_excluded_path(rel, exclude_prefixes):
            report.skipped += 1
            continue

        report.concepts_checked += 1
        path = docs_root / rel
        text = path.read_text(encoding="utf-8", errors="replace")

        try:
            doc = OKFDocument.parse(text)
        except OKFDocumentError as exc:
            report.findings.append(
                LintFinding(rel, "frontmatter_parse", str(exc), "error")
            )
            continue

        if profile == "minimal":
            _check_minimal(report, rel, doc)
        else:
            _check_vexlum(report, rel, doc, bundle_name)

        for raw, resolved in collect_markdown_links(text, path, docs_root):
            if resolved is None:
                continue
            if resolved not in all_md_set:
                target = docs_root / resolved
                if not target.exists():
                    report.findings.append(
                        LintFinding(
                            rel,
                            "broken_internal_link",
                            f"Link target missing: {raw!r} -> {resolved}",
                            "warning",
                        )
                    )

    return report


def _check_minimal(report: BundleReport, rel: str, doc: OKFDocument) -> None:
    if not doc.has_frontmatter:
        report.findings.append(
            LintFinding(rel, "missing_frontmatter", "Concept lacks YAML frontmatter", "error")
        )
        return
    type_val = doc.frontmatter.get("type")
    if not type_val or not str(type_val).strip():
        report.findings.append(
            LintFinding(rel, "missing_type", "Frontmatter field 'type' is required", "error")
        )


def _check_vexlum(report: BundleReport, rel: str, doc: OKFDocument, bundle_name: str) -> None:
    _check_minimal(report, rel, doc)
    if not doc.has_frontmatter:
        return

    for key in VEXLUM_PROFILE_FIELDS:
        if key == "type":
            continue
        value = doc.frontmatter.get(key)
        if value is None or value == "" or (isinstance(value, (list, dict)) and not value):
            report.findings.append(
                LintFinding(
                    rel,
                    f"missing_{key}",
                    f"Vexlum profile requires frontmatter field '{key}'",
                    "warning",
                )
            )

    resource = doc.frontmatter.get("resource")
    if resource:
        expected = expected_resource_paths(rel, bundle_name)
        normalized = str(resource).replace("\\", "/")
        if normalized not in expected:
            report.findings.append(
                LintFinding(
                    rel,
                    "resource_mismatch",
                    f"resource {resource!r} does not match expected one of {sorted(expected)!r}",
                    "warning",
                )
            )

    ts_err = validate_timestamp(doc.frontmatter.get("timestamp"))
    if ts_err and doc.frontmatter.get("timestamp") is not None:
        report.findings.append(LintFinding(rel, "invalid_timestamp", ts_err, "warning"))

    tags = doc.frontmatter.get("tags")
    if tags is not None and not isinstance(tags, list):
        report.findings.append(
            LintFinding(rel, "invalid_tags", "tags must be a YAML list", "warning")
        )


def print_text_report(report: BundleReport) -> None:
    counts = report.counts()
    print(f"=== OKF lint: {report.bundle_root} ({report.bundle_name}) ===")
    print(
        f"profile={report.profile} md={report.total_md} "
        f"concepts_checked={report.concepts_checked} skipped={report.skipped} "
        f"errors={counts['error']} warnings={counts['warning']} info={counts['info']}"
    )
    if not report.findings:
        print("OK — no findings")
        print()
        return

    by_severity: dict[str, list[LintFinding]] = {s: [] for s in SEVERITIES}
    for finding in report.findings:
        by_severity[finding.severity].append(finding)

    for severity in SEVERITIES:
        items = by_severity[severity]
        if not items:
            continue
        print(f"\n{severity.upper()} ({len(items)}):")
        for item in items[:50]:
            print(f"  [{item.code}] {item.path}: {item.message}")
        if len(items) > 50:
            print(f"  ... and {len(items) - 50} more")
    print()


def report_to_dict(report: BundleReport) -> dict:
    data = asdict(report)
    data["counts"] = report.counts()
    return data


def build_parser() -> argparse.ArgumentParser:
    default_docs = Path(__file__).resolve().parents[1] / "docs"
    parser = argparse.ArgumentParser(description="Lint an OKF-aligned docs/ bundle")
    parser.add_argument(
        "bundle_roots",
        nargs="*",
        type=Path,
        help=f"Bundle root directories (default: {default_docs})",
    )
    parser.add_argument(
        "--profile",
        choices=PROFILES,
        default="vexlum",
        help="minimal = OKF v0.1 (type only); vexlum = local agent profile (default)",
    )
    parser.add_argument(
        "--bundle-name",
        default="docs",
        help="Label used in resource path validation (default: docs)",
    )
    parser.add_argument(
        "--exclude-prefix",
        action="append",
        default=["archive/"],
        dest="exclude_prefixes",
        help="Skip frontmatter checks for paths under this prefix (repeatable)",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    parser.add_argument(
        "--fail-on",
        choices=SEVERITIES,
        default="error",
        help="Exit non-zero when findings at or above this severity exist",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=None,
        dest="only_paths",
        metavar="REL_PATH",
        help="Lint only bundle-relative paths (repeatable; e.g. guides/foo.md)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    roots = args.bundle_roots or [Path(__file__).resolve().parents[1] / "docs"]
    exclude = tuple(args.exclude_prefixes or ())
    only = frozenset(args.only_paths) if args.only_paths else None

    reports: list[BundleReport] = []
    for root in roots:
        reports.append(
            lint_bundle(
                root,
                profile=args.profile,
                bundle_name=args.bundle_name,
                exclude_prefixes=exclude,
                only_paths=only,
            )
        )

    if args.json:
        print(json.dumps([report_to_dict(r) for r in reports], indent=2))
    else:
        for report in reports:
            print_text_report(report)

    severity_rank = {s: i for i, s in enumerate(SEVERITIES)}
    threshold = severity_rank[args.fail_on]
    for report in reports:
        for finding in report.findings:
            if severity_rank[finding.severity] <= threshold:
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
