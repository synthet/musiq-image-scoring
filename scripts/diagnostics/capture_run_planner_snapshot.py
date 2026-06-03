#!/usr/bin/env python3
"""Capture enqueue vs live JIT planner stats for a run id (diagnostics)."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

DEFAULT_BASE = "http://127.0.0.1:7860"


def _get(base: str, path: str) -> dict:
    with urllib.request.urlopen(f"{base.rstrip('/')}{path}", timeout=120) as resp:
        return json.loads(resp.read())


def _post(base: str, path: str, body: dict) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{base.rstrip('/')}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id", type=int, help="jobs.id / run id")
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    args = parser.parse_args()

    try:
        job = _get(args.base_url, f"/api/jobs/{args.run_id}")
    except urllib.error.URLError as exc:
        print(f"Failed to fetch job: {exc}", file=sys.stderr)
        return 1

    payload = job.get("queue_payload") or {}
    folder = payload.get("input_path") or (payload.get("scope_paths") or [None])[0]
    stages = payload.get("target_phases") or payload.get("phases") or []

    print(f"run_id={args.run_id} status={job.get('status')}")
    print(f"folder={folder}")
    print(f"target_phases={stages}")
    rp = payload.get("repair_plan_summary") or {}
    sq = rp.get("stage_queues") or {}
    print("enqueue_stage_queues:", {k: len(v) for k, v in sq.items() if isinstance(v, list)})
    print("enqueue_issue_counts_by_reason:", rp.get("issue_counts_by_reason"))

    if folder and stages:
        preview = _post(
            args.base_url,
            "/api/runs/plan/preview",
            {"scope_paths": [folder], "stages": list(stages)},
        )
        sq2 = preview.get("stage_queues") or {}
        print("live_stage_queues:", {k: len(v) for k, v in sq2.items() if isinstance(v, list)})
        print("live_issue_counts_by_reason:", preview.get("issue_counts_by_reason"))
        scoring_ids = sq2.get("scoring") or []
        if scoring_ids:
            print("sample_scoring_ids:", scoring_ids[:5])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
