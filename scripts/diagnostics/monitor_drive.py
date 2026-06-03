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


def _collect_anomalies(payload: dict[str, Any], *, local_diag: dict[str, Any] | None) -> tuple[list[str], list[str]]:
    """Return (warnings, errors). Warnings do not stop continuous monitoring."""
    warnings: list[str] = []
    errors: list[str] = []
    state = payload.get("state") or {}
    outstanding = payload.get("outstanding") or {}
    last_result = state.get("last_result") or {}
    health = last_result.get("health") or outstanding.get("health") or {}

    loop_detected = int(last_result.get("loop_detected") or 0)
    if loop_detected > 0:
        warnings.append(f"loop_detected={loop_detected} on last tick")

    stop_reason = state.get("stop_reason")
    schedulable = int(health.get("schedulable_folders") or 0)
    if stop_reason == "stalled" and schedulable > 0:
        errors.append(f"stalled_with_schedulable_work (schedulable={schedulable})")

    if local_diag:
        for item in local_diag.get("anomalies") or []:
            code = item.get("code") or "anomaly"
            msg = item.get("message") or ""
            line = f"{code}: {msg}".strip(": ")
            severity = str(item.get("severity") or "").lower()
            if severity == "error":
                errors.append(line)
            else:
                warnings.append(line)

    return warnings, errors


def _print_human(payload: dict[str, Any], warnings: list[str], errors: list[str], *, header: str = "") -> None:
    if header:
        print(header)
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
    if errors:
        print("Errors:")
        for f in errors:
            print(f"  - {f}")
    if warnings:
        print("Warnings:")
        for f in warnings:
            print(f"  - {f}")
    if not errors and not warnings:
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
        warnings, errors = _collect_anomalies(payload, local_diag=local_diag)
        if args.json:
            out = {
                "status": payload,
                "warnings": warnings,
                "errors": errors,
                "healthy": not errors,
            }
            if local_diag:
                out["local_diagnostics"] = local_diag
            print(json.dumps(out, indent=2))
        else:
            _print_human(payload, warnings, errors)
        if errors:
            return 1
        if warnings and args.once:
            return 1
        return 0

    if args.once:
        return run_once()

    poll_n = 0
    while True:
        poll_n += 1
        header = f"--- poll {poll_n} @ {time.strftime('%H:%M:%S')} ---"
        try:
            payload = _fetch_status(args.base_url)
        except urllib.error.URLError as exc:
            print(f"{header}\nFailed to reach {args.base_url}: {exc}", file=sys.stderr)
            return 2
        local_diag = _fetch_diagnostics_local() if args.local_diagnostics else None
        warnings, errors = _collect_anomalies(payload, local_diag=local_diag)
        if args.json:
            out = {
                "poll": poll_n,
                "status": payload,
                "warnings": warnings,
                "errors": errors,
                "healthy": not errors,
            }
            if local_diag:
                out["local_diagnostics"] = local_diag
            print(json.dumps(out, indent=2))
        else:
            _print_human(payload, warnings, errors, header=header)
            print()
        if errors:
            return 1
        time.sleep(max(0.5, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
