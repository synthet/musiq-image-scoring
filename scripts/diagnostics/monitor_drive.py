#!/usr/bin/env python3
"""Poll auto-drive status and flag scheduling anomalies.

Examples:
  python scripts/diagnostics/monitor_drive.py --once
  python scripts/diagnostics/monitor_drive.py --interval 10 --json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any


def _fetch_status(base_url: str) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/runs/drive/status"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fetch_diagnostics_local() -> dict[str, Any] | None:
    try:
        from modules import runs_autodrive

        return runs_autodrive.get_drive_diagnostics()
    except Exception:
        return None


def _collect_anomalies(payload: dict[str, Any], *, local_diag: dict[str, Any] | None) -> list[str]:
    flags: list[str] = []
    state = payload.get("state") or {}
    outstanding = payload.get("outstanding") or {}
    last_result = state.get("last_result") or {}
    health = last_result.get("health") or outstanding.get("health") or {}

    loop_detected = int(last_result.get("loop_detected") or 0)
    if loop_detected > 0:
        flags.append(f"loop_detected={loop_detected} on last tick")

    stop_reason = state.get("stop_reason")
    schedulable = int(health.get("schedulable_folders") or 0)
    if stop_reason == "stalled" and schedulable > 0:
        flags.append(f"stalled_with_schedulable_work (schedulable={schedulable})")

    if local_diag:
        for item in local_diag.get("anomalies") or []:
            code = item.get("code") or "anomaly"
            msg = item.get("message") or ""
            flags.append(f"{code}: {msg}".strip(": "))

    return flags


def _print_human(payload: dict[str, Any], flags: list[str]) -> None:
    state = payload.get("state") or {}
    outstanding = payload.get("outstanding") or {}
    last_result = state.get("last_result") or {}
    health = last_result.get("health") or outstanding.get("health") or {}

    enabled = "yes" if state.get("enabled") else "no"
    print(f"Driving: {enabled}")
    if state.get("root_path"):
        print(f"Scope: {state.get('root_path')}")
    print(f"Outstanding folders: {outstanding.get('total_outstanding')}")
    print(
        "Health: "
        f"in_flight={health.get('in_flight_folders', 0)} "
        f"schedulable={health.get('schedulable_folders', 0)} "
        f"blocked={health.get('blocked_folders', 0)}"
    )
    if last_result:
        print(
            "Last tick: "
            f"reason={last_result.get('last_tick_reason', '—')} "
            f"queued={last_result.get('scheduled', 0)} "
            f"skipped={last_result.get('skipped', 0)} "
            f"loop_detected={last_result.get('loop_detected', 0)}"
        )
    if state.get("stop_reason"):
        print(f"Stop reason: {state.get('stop_reason')}")
    bucket_counts = outstanding.get("bucket_counts") or last_result.get("bucket_counts") or {}
    if bucket_counts:
        parts = ", ".join(f"{k}={v}" for k, v in sorted(bucket_counts.items()))
        print(f"Buckets: {parts}")
    if flags:
        print("Anomalies:")
        for f in flags:
            print(f"  - {f}")
    else:
        print("Anomalies: none")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Monitor Runs auto-drive health")
    parser.add_argument("--base-url", default="http://127.0.0.1:7860", help="WebUI base URL")
    parser.add_argument("--interval", type=float, default=5.0, help="Poll interval seconds")
    parser.add_argument("--once", action="store_true", help="Single snapshot then exit")
    parser.add_argument("--json", action="store_true", help="Emit JSON snapshot")
    parser.add_argument(
        "--local-diagnostics",
        action="store_true",
        help="Merge modules.runs_autodrive.get_drive_diagnostics() when importable (WSL app env)",
    )
    args = parser.parse_args(argv)

    def run_once() -> int:
        try:
            payload = _fetch_status(args.base_url)
        except urllib.error.URLError as exc:
            print(f"Failed to reach {args.base_url}: {exc}", file=sys.stderr)
            return 2
        local_diag = _fetch_diagnostics_local() if args.local_diagnostics else None
        flags = _collect_anomalies(payload, local_diag=local_diag)
        if args.json:
            out = {"status": payload, "anomalies": flags, "healthy": not flags}
            if local_diag:
                out["local_diagnostics"] = local_diag
            print(json.dumps(out, indent=2))
        else:
            _print_human(payload, flags)
        return 1 if flags else 0

    if args.once:
        return run_once()

    while True:
        code = run_once()
        if code != 0:
            return code
        time.sleep(max(0.5, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
