#!/usr/bin/env python3
"""Import Cursor agent transcripts into per-repo lesson staging or raw-sessions."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.agent_memory.transcripts import (  # noqa: E402
    TranscriptRecord,
    build_record,
    consolidate_repo_candidates,
    dedupe_transcripts,
    discover_parent_transcripts,
    extract_heuristic_candidates,
    filter_candidates_for_repo,
    group_records_by_repo,
    load_authority_corpus,
    load_workspace_config,
    record_to_session_yaml,
    render_review_markdown,
    render_summary_report,
    resolve_repo_path,
    write_session_files,
)

CONFIG_DIR = _ROOT / "scripts" / "transcript_mining"


def main() -> int:
    parser = argparse.ArgumentParser(description="Mine Cursor agent transcripts")
    parser.add_argument(
        "--cursor-projects",
        type=Path,
        default=None,
        help="Path to ~/.cursor/projects",
    )
    parser.add_argument("--repo", default=None, help="Filter to one repo folder name")
    parser.add_argument(
        "--min-relevance",
        type=float,
        default=0.25,
        help="Minimum relevance score (0-1)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write session YAML files",
    )
    parser.add_argument(
        "--write-sessions",
        action="store_true",
        help="Write .agent-memory/raw-sessions/*.yaml for tier-A repos",
    )
    parser.add_argument(
        "--no-consolidate",
        action="store_true",
        help="Write one YAML per chat instead of one consolidated session per repo",
    )
    parser.add_argument(
        "--no-mirror-staging",
        action="store_true",
        help="Do not copy staging into each repo under .agent/scratch/transcript-mining/",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Write summary report markdown path",
    )
    parser.add_argument(
        "--staging-root",
        type=Path,
        default=_ROOT / ".agent" / "scratch" / "transcript-mining",
        help="Per-repo REVIEW.md and candidates.json output directory",
    )
    args = parser.parse_args()

    workspace_map, repo_profiles, projects_root, default_cursor = load_workspace_config(
        CONFIG_DIR
    )
    cursor_projects = args.cursor_projects or default_cursor
    if not cursor_projects.is_dir():
        print(f"Cursor projects dir not found: {cursor_projects}", file=sys.stderr)
        return 1

    known_repos = set(repo_profiles.keys())
    entries = discover_parent_transcripts(cursor_projects)
    deduped = dedupe_transcripts(entries)

    workspaces_cfg = workspace_map.get("workspaces") or {}
    records = []
    for uuid, (workspace, path, mtime) in deduped.items():
        ws_repos = workspaces_cfg.get(workspace, {}).get("repos") or []
        record = build_record(uuid, workspace, path, mtime, known_repos, ws_repos)
        if record.relevance < args.min_relevance:
            continue
        if args.repo and record.primary_repo != args.repo:
            if args.repo not in ws_repos and record.primary_repo != args.repo:
                continue
        records.append(record)

    grouped = group_records_by_repo(records, workspace_map)
    if args.repo:
        grouped = {k: v for k, v in grouped.items() if k == args.repo}

    staging_root: Path = args.staging_root
    staging_root.mkdir(parents=True, exist_ok=True)

    all_candidates: dict[str, dict[str, list[dict[str, str]]]] = {}
    sessions_to_write: dict[str, list[dict]] = {}

    for repo_name, repo_records in grouped.items():
        if repo_name == "_unassigned":
            continue
        repo_root = resolve_repo_path(projects_root, repo_name)
        authority = ""
        if repo_root.is_dir():
            authority = load_authority_corpus(repo_root)
        profile = repo_profiles.get(repo_name, {"tier": "C"})

        candidates_by_uuid: dict[str, list[dict[str, str]]] = {}
        repo_candidates_flat: list[dict] = []
        session_payloads: list[dict] = []

        for rec in repo_records:
            raw_cands = extract_heuristic_candidates(rec)
            safe = filter_candidates_for_repo(raw_cands, authority)
            if not safe:
                continue
            candidates_by_uuid[rec.uuid] = safe
            for cand in safe:
                repo_candidates_flat.append(
                    {
                        **cand,
                        "transcript_uuid": rec.uuid,
                        "relevance": rec.relevance,
                        "task_summary": rec.task_summary,
                    }
                )
            if safe and profile.get("tier") == "A" and profile.get("has_agent_memory"):
                session_payloads.append(record_to_session_yaml(rec, safe))

        all_candidates[repo_name] = candidates_by_uuid

        repo_staging = staging_root / repo_name
        repo_staging.mkdir(parents=True, exist_ok=True)
        (repo_staging / "candidates.json").write_text(
            json.dumps(repo_candidates_flat, indent=2),
            encoding="utf-8",
        )
        (repo_staging / "REVIEW.md").write_text(
            render_review_markdown(repo_name, repo_records, candidates_by_uuid, profile),
            encoding="utf-8",
        )

        if not args.no_mirror_staging and repo_root.is_dir():
            dest = repo_root / ".agent" / "scratch" / "transcript-mining"
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(repo_staging / "REVIEW.md", dest / "REVIEW.md")
            shutil.copy2(repo_staging / "candidates.json", dest / "candidates.json")

        if (
            candidates_by_uuid
            and profile.get("tier") == "A"
            and profile.get("has_agent_memory")
            and args.write_sessions
            and not args.dry_run
            and repo_root.is_dir()
        ):
            if args.no_consolidate:
                sessions_to_write[repo_name] = session_payloads
            else:
                merged = consolidate_repo_candidates(repo_records, candidates_by_uuid)
                if merged:
                    pseudo = TranscriptRecord(
                        uuid="transcript-mining-batch1",
                        workspace="import_transcripts",
                        path=Path("consolidated"),
                        mtime=datetime.now(timezone.utc).timestamp(),
                        user_queries=[
                            "Consolidated transcript mining batch 1 "
                            "(WSL, pytest, MCP, E2E naming, cross-repo)"
                        ],
                        relevance=1.0,
                        themes=sorted({t for r in repo_records for t in r.themes})[:12],
                    )
                    payload = record_to_session_yaml(pseudo, merged)
                    payload["source_transcript_uuid"] = "transcript-mining-batch1"
                    sessions_to_write[repo_name] = [payload]

    summary = render_summary_report(records, grouped, repo_profiles)
    summary_path = args.report or staging_root / (
        datetime.now(timezone.utc).strftime("%Y-%m-%d") + "-report.md"
    )
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(summary, encoding="utf-8")

    written_count = 0
    for repo_name, payloads in sessions_to_write.items():
        repo_root = resolve_repo_path(projects_root, repo_name)
        paths = write_session_files(repo_root, payloads, dry_run=args.dry_run)
        written_count += len(paths)
        print(f"Wrote {len(paths)} session(s) to {repo_root / '.agent-memory/raw-sessions'}")

    print(summary_path)
    print(f"Staging: {staging_root}")
    print(f"Records: {len(records)} chats, {len(grouped)} repos, sessions written: {written_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
