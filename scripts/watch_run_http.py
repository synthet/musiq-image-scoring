#!/usr/bin/env python3
"""
Poll a pipeline run (jobs.id) over HTTP until it reaches a terminal status.

Uses the same JSON as the React Runs UI: GET /api/jobs/{id} (includes job_phases rows).

Examples (WebUI on 7860):

  python scripts/watch_run_http.py 2365
  python scripts/watch_run_http.py 2365 --interval 5
  python scripts/watch_run_http.py 2365 --once --verbose
  python scripts/watch_run_http.py 2365 --wsl-gateway

Requires the FastAPI app to be reachable (no auth in default local dev).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

TERMINAL = frozenset(
    {"completed", "failed", "interrupted", "canceled", "cancelled", "complete", "done"}
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S%z")


def _detect_wsl_default_gateway_webui(port: int = 7860) -> str | None:
    """WSL2: Windows host is often `nameserver` in /etc/resolv.conf — not 127.0.0.1."""
    try:
        with open("/etc/resolv.conf", encoding="utf-8") as f:
            for line in f:
                ls = line.strip()
                if ls.startswith("nameserver"):
                    ip = ls.split()[1].strip()
                    if ip:
                        return f"http://{ip}:{port}"
    except OSError:
        return None
    return None


def _load_json(url: str, timeout: float = 30.0) -> Any:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def _get_json(url: str, timeout: float = 30.0) -> dict[str, Any]:
    data = _load_json(url, timeout)
    if not isinstance(data, dict):
        raise TypeError(f"Expected JSON object from {url}, got {type(data).__name__}")
    return data


def _phases_line(phases: list[dict[str, Any]] | None) -> str:
    if not phases:
        return "(no phases in payload)"
    parts: list[str] = []
    for p in sorted(phases, key=lambda x: int(x.get("phase_order") or 0)):
        code = str(p.get("phase_code") or "?")
        state = str(p.get("state") or "?")
        parts.append(f"{code}={state}")
    return " | ".join(parts)


def _stages_line(stages: list[dict[str, Any]] | None) -> str:
    if not stages:
        return ""
    parts: list[str] = []
    for s in stages:
        code = str(s.get("phase_code") or "?")
        state = str(s.get("state") or "?")
        done = s.get("items_done")
        total = s.get("items_total")
        if done is not None and total is not None:
            parts.append(f"{code}={state}({done}/{total})")
        else:
            parts.append(f"{code}={state}")
    return "stages: " + " | ".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description="Poll GET /api/jobs/{run_id} until terminal status.")
    ap.add_argument("run_id", type=int, help="jobs.id (same as /ui/runs/:id)")
    ap.add_argument(
        "--wsl-gateway",
        action="store_true",
        help="Use Windows host IP from /etc/resolv.conf nameserver (:7860) — needed when Python runs "
        "in WSL but the WebUI listens on Windows localhost",
    )
    ap.add_argument(
        "--base-url",
        default="http://127.0.0.1:7860",
        help="WebUI root (default: %(default)s). With WSL targeting a Windows-hosted WebUI, add --wsl-gateway.",
    )
    ap.add_argument(
        "--port",
        type=int,
        default=7860,
        help="Implicit port when using --wsl-gateway (default: %(default)s)",
    )
    ap.add_argument(
        "--interval",
        type=float,
        default=15.0,
        help="Seconds between polls (default: %(default)s)",
    )
    ap.add_argument("--once", action="store_true", help="Single request and exit")
    ap.add_argument(
        "--verbose",
        action="store_true",
        help="Also GET /api/runs/{id}/stages when items_* are populated",
    )
    ap.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout seconds")
    args = ap.parse_args()

    base_url = args.base_url
    if args.wsl_gateway:
        gw = _detect_wsl_default_gateway_webui(port=args.port)
        if gw:
            base_url = gw
            print(f"Using WSL gateway as base URL: {base_url}", flush=True)

    base = base_url.rstrip("/")
    job_url = f"{base}/api/jobs/{args.run_id}"
    stages_url = f"{base}/api/runs/{args.run_id}/stages"

    print(f"Watching run {args.run_id} ← {job_url}", flush=True)
    print(f"Interval {args.interval}s (Ctrl+C to stop)\n", flush=True)

    while True:
        try:
            job = _get_json(job_url, timeout=args.timeout)
        except urllib.error.HTTPError as e:
            print(f"[{_iso_now()}] HTTP {e.code}: {e.reason}", file=sys.stderr, flush=True)
            if args.once:
                return 1
            time.sleep(args.interval)
            continue
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
            print(f"[{_iso_now()}] error: {e}", file=sys.stderr, flush=True)
            if args.once:
                return 1
            time.sleep(args.interval)
            continue

        status = str(job.get("status") or "").strip().lower()
        jt = str(job.get("job_type") or "")
        phases = job.get("phases")
        phase_list = phases if isinstance(phases, list) else None

        extra = ""
        if args.verbose:
            try:
                stages_raw = _load_json(stages_url, timeout=args.timeout)
                if isinstance(stages_raw, list):
                    sd = [x for x in stages_raw if isinstance(x, dict)]
                    seg = _stages_line(sd)
                    if seg:
                        extra = " " + seg
            except (
                urllib.error.HTTPError,
                urllib.error.URLError,
                TimeoutError,
                OSError,
                json.JSONDecodeError,
                TypeError,
            ):
                extra = ""

        print(
            f"[{_iso_now()}] status={status!r} job_type={jt!r} {_phases_line(phase_list if phase_list else None)}{extra}",
            flush=True,
        )

        if status in TERMINAL:
            print(f"\nTerminal status reached: {status!r}", flush=True)
            return 0 if status not in {"failed", "interrupted"} else 2

        if args.once:
            return 0

        time.sleep(max(1.0, args.interval))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nStopped by user.", flush=True)
        raise SystemExit(130) from None
