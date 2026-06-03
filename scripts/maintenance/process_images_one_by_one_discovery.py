#!/usr/bin/env python3
"""
One-by-one full discovery: queue indexing → metadata → scoring → keywords per image
via POST /api/runs/submit, then wait until the run finishes before submitting the next.

Uses run_mode=process_stale_or_missing (canonical) so the JIT planner selects
stale/missing image×phase work only.

Examples (WebUI must be running; from WSL with project venv):

  # Paths from a file (one absolute path per line)
  python scripts/maintenance/process_images_one_by_one_discovery.py \\
    --paths-file paths.txt --base-url http://127.0.0.1:7860

  # Same, but WebUI on Windows while this script runs in WSL2
  python scripts/maintenance/process_images_one_by_one_discovery.py \\
    --paths-file paths.txt --wsl-gateway

  # Discover candidates via DB (scoring-incomplete rows; same criteria as get_incomplete_records)
  python scripts/maintenance/process_images_one_by_one_discovery.py \\
    --discover-scoring-incomplete --limit 50 --dry-run

  # Keep scheduling broken (scoring-incomplete) images one at a time until none remain
  python scripts/maintenance/process_images_one_by_one_discovery.py \\
    --discover-scoring-incomplete --loop-until-empty --max-runs 0 \\
    --base-url http://127.0.0.1:7860

  # Export paths from your own SQL (one column file_path per line), then --paths-file.

Requires HTTP access to the FastAPI app (default local dev has no auth).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Iterable

DEFAULT_STAGES = ["indexing", "metadata", "scoring", "keywords"]
DEFAULT_RUN_MODE = "process_stale_or_missing"

JOB_TERMINAL = frozenset(
    {
        "completed",
        "failed",
        "interrupted",
        "canceled",
        "cancelled",
        # Belt-and-suspenders: tolerate legacy / alternate job row spellings.
        "complete",
        "done",
    }
)
STAGE_TERMINAL = frozenset({"completed", "skipped", "failed", "canceled", "cancelled"})


def _format_log_ts() -> str:
    """Wall-clock stamp for log lines (ISO-8601 with local offset)."""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _detect_wsl_default_gateway_webui(port: int = 7860) -> str | None:
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


def _load_json(url: str, *, timeout: float = 60.0, data: bytes | None = None, method: str = "GET") -> Any:
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Accept": "application/json"},
    )
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def _get_json(url: str, timeout: float = 60.0) -> dict[str, Any]:
    data = _load_json(url, timeout=timeout)
    if not isinstance(data, dict):
        raise TypeError(f"Expected JSON object from {url}, got {type(data).__name__}")
    return data


def _post_json(url: str, body: dict[str, Any], timeout: float = 120.0) -> dict[str, Any]:
    payload = json.dumps(body).encode("utf-8")
    data = _load_json(url, timeout=timeout, data=payload, method="POST")
    if not isinstance(data, dict):
        raise TypeError(f"Expected JSON object from POST {url}, got {type(data).__name__}")
    return data


def _stages_all_terminal(stages: list[dict[str, Any]]) -> bool:
    if not stages:
        return False
    for row in stages:
        st = str(row.get("state") or "").strip().lower()
        if st not in STAGE_TERMINAL:
            return False
    return True


def _read_paths_from_file(path: str) -> list[str]:
    out: list[str] = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            out.append(s)
    return out


def _read_paths_from_stdin() -> list[str]:
    out: list[str] = []
    for line in sys.stdin:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s)
    return out


def _discover_scoring_incomplete_paths(limit: int) -> list[str]:
    """Resolve file_path for rows that fail scoring completeness (DB must match WebUI)."""
    from modules import db

    rows = db.get_incomplete_records(limit)
    paths: list[str] = []
    for r in rows or []:
        fp = r.get("file_path")
        if fp and str(fp).strip():
            paths.append(str(fp).strip())
    return paths


def _count_incomplete() -> int:
    from modules import db

    return int(db.count_incomplete_records())


def _maybe_localize_path_for_client(file_path: str) -> str:
    """If running on Windows and path looks like WSL /mnt/, try D:\\ style via project utils."""
    if os.name != "nt":
        return file_path
    sl = file_path.replace("\\", "/")
    if not sl.startswith("/mnt/"):
        return file_path
    try:
        from modules import utils

        if hasattr(utils, "convert_path_to_local"):
            local = utils.convert_path_to_local(file_path)
            if local and os.path.exists(local):
                return local
    except Exception:
        pass
    return file_path


def submit_discovery_run(
    base: str,
    file_path: str,
    *,
    stages: list[str],
    run_mode: str,
    generate_captions: bool,
    timeout: float,
) -> int:
    url = f"{base}/api/runs/submit"
    body: dict[str, Any] = {
        "scope_type": "file",
        "scope_paths": [file_path],
        "stages": list(stages),
        "run_mode": run_mode,
        "generate_captions": bool(generate_captions),
    }
    resp = _post_json(url, body, timeout=timeout)
    if not resp.get("success"):
        raise RuntimeError(f"runs/submit failed: {resp!r}")
    run_id = resp.get("run_id")
    if run_id is None:
        raise RuntimeError(f"runs/submit missing run_id: {resp!r}")
    return int(run_id)


def wait_until_run_finished(
    base: str,
    run_id: int,
    *,
    poll_interval: float,
    timeout: float,
    per_request_timeout: float,
) -> tuple[str, list[dict[str, Any]] | None]:
    """Poll stages until all terminal or job status is terminal. Returns (job_status, last_stages)."""
    job_url = f"{base}/api/jobs/{run_id}"
    stages_url = f"{base}/api/runs/{run_id}/stages"
    deadline = time.monotonic() + timeout
    last_stages: list[dict[str, Any]] | None = None

    while time.monotonic() < deadline:
        try:
            job = _get_json(job_url, timeout=per_request_timeout)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
            raise RuntimeError(f"GET {job_url} failed: {e}") from e

        jstatus = str(job.get("status") or "").strip().lower()
        if jstatus in JOB_TERMINAL:
            try:
                raw = _load_json(stages_url, timeout=per_request_timeout)
                if isinstance(raw, list):
                    last_stages = [x for x in raw if isinstance(x, dict)]
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
                last_stages = None
            return jstatus, last_stages

        try:
            raw = _load_json(stages_url, timeout=per_request_timeout)
            if isinstance(raw, list):
                last_stages = [x for x in raw if isinstance(x, dict)]
                if last_stages and _stages_all_terminal(last_stages):
                    # Job row may lag slightly; re-fetch job once
                    job2 = _get_json(job_url, timeout=per_request_timeout)
                    return str(job2.get("status") or "").strip().lower(), last_stages
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            pass

        time.sleep(max(1.0, poll_interval))

    raise TimeoutError(f"Run {run_id} did not finish within {timeout}s")


def _format_stages(stages: list[dict[str, Any]] | None) -> str:
    if not stages:
        return ""
    parts = []
    for s in stages:
        code = str(s.get("phase_code") or "?")
        state = str(s.get("state") or "?")
        parts.append(f"{code}={state}")
    return " | ".join(parts)


def _process_one_file(
    *,
    base: str,
    fp: str,
    idx: int,
    total: int | None,
    stages: list[str],
    args: argparse.Namespace,
) -> tuple[bool, str | None]:
    """Submit one run and wait. Returns (ok, job_status_lower_or_none)."""
    label = f"[{idx}/{total}]" if total is not None else f"[#{idx}]"
    if args.localize_paths_on_windows:
        fp = _maybe_localize_path_for_client(fp)

    if args.strict_path_check and not os.path.exists(fp):
        print(f"[{_format_log_ts()}] {label} SKIP (not on this host): {fp}", flush=True)
        return False, None

    print(f"[{_format_log_ts()}] {label} {fp}", flush=True)
    if args.dry_run:
        print("  dry-run: would POST /api/runs/submit scope_type=file scope_paths=[...]", flush=True)
        return True, "completed"

    try:
        run_id = submit_discovery_run(
            base,
            fp,
            stages=stages,
            run_mode=args.run_mode,
            generate_captions=args.generate_captions,
            timeout=args.submit_timeout,
        )
        print(f"  run_id={run_id} — waiting…", flush=True)
        jstatus, st = wait_until_run_finished(
            base,
            run_id,
            poll_interval=args.poll_interval,
            timeout=args.wait_timeout,
            per_request_timeout=args.http_timeout,
        )
        seg = _format_stages(st)
        if seg:
            print(f"  job_status={jstatus!r}  {seg}", flush=True)
        else:
            print(f"  job_status={jstatus!r}", flush=True)
        if jstatus in {"failed", "interrupted"}:
            return False, jstatus
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        print(f"  ERROR ({type(e).__name__}): {e}", file=sys.stderr, flush=True)
        return False, None
    except Exception as e:
        print(f"  ERROR ({type(e).__name__}): {e}", file=sys.stderr, flush=True)
        return False, None

    time.sleep(max(0.0, float(args.sleep_between_runs)))
    return True, jstatus


def iter_paths(args: argparse.Namespace) -> Iterable[str]:
    if args.paths_file:
        yield from _read_paths_from_file(args.paths_file)
    elif args.stdin_paths:
        yield from _read_paths_from_stdin()
    elif args.discover_scoring_incomplete:
        lim = int(args.limit) if args.limit > 0 else 500
        if args.limit <= 0:
            print(
                "Note: --discover-scoring-incomplete without positive --limit defaults to 500 rows; "
                "pass e.g. --limit 5000 for more.",
                flush=True,
            )
        yield from _discover_scoring_incomplete_paths(lim)
    else:
        yield from ()


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Submit full discovery (indexing→metadata→scoring→keywords) one image at a time "
        "via /api/runs/submit and wait for each run to finish.",
    )
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "--paths-file",
        metavar="FILE",
        help="Text file: one absolute file_path per line (# comments allowed).",
    )
    src.add_argument(
        "--stdin-paths",
        action="store_true",
        help="Read paths from stdin (one per line).",
    )
    src.add_argument(
        "--discover-scoring-incomplete",
        action="store_true",
        help="Use DB get_incomplete_records (requires modules/db on PYTHONPATH; run from WSL app venv).",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=0,
        help="With --discover-scoring-incomplete: max rows from DB (default 500 when omitted or 0).",
    )
    ap.add_argument(
        "--base-url",
        default="http://127.0.0.1:7860",
        help="WebUI root (default: %(default)s).",
    )
    ap.add_argument(
        "--wsl-gateway",
        action="store_true",
        help="Use Windows host from /etc/resolv.conf nameserver with --port (WSL2 → Windows WebUI).",
    )
    ap.add_argument("--port", type=int, default=7860, help="Port for --wsl-gateway (default: %(default)s)")
    ap.add_argument(
        "--localize-paths-on-windows",
        action="store_true",
        help="When on Windows, try convert_path_to_local for /mnt/... paths before POST (server must still see files).",
    )
    ap.add_argument(
        "--strict-path-check",
        action="store_true",
        help="Skip paths where os.path.exists is false on this machine (optional; server may still see them).",
    )
    ap.add_argument(
        "--stages",
        default=",".join(DEFAULT_STAGES),
        help="Comma-separated stage codes (default: %(default)s).",
    )
    ap.add_argument(
        "--run-mode",
        default=DEFAULT_RUN_MODE,
        help="runs/submit run_mode (default: %(default)s).",
    )
    ap.add_argument(
        "--generate-captions",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="BLIP captions during keywords (default: true).",
    )
    ap.add_argument("--poll-interval", type=float, default=5.0, help="Seconds between polls (default: %(default)s)")
    ap.add_argument(
        "--wait-timeout",
        type=float,
        default=7200.0,
        help="Max seconds to wait per run (default: %(default)s).",
    )
    ap.add_argument("--http-timeout", type=float, default=60.0, help="Per HTTP request timeout (default: %(default)s)")
    ap.add_argument("--submit-timeout", type=float, default=120.0, help="POST /api/runs/submit timeout (default: %(default)s)")
    ap.add_argument(
        "--loop-until-empty",
        action="store_true",
        help="With --discover-scoring-incomplete: repeatedly fetch the next single incomplete image, "
        "run full discovery, wait until done, then re-query DB until no rows remain (or --max-runs).",
    )
    ap.add_argument(
        "--max-runs",
        type=int,
        default=0,
        help="With --loop-until-empty: stop after this many submitted runs (0 = no cap).",
    )
    ap.add_argument(
        "--sleep-between-runs",
        type=float,
        default=2.0,
        help="Seconds to sleep after each run reaches a terminal job status (default: %(default)s).",
    )
    ap.add_argument(
        "--max-same-path-retries",
        type=int,
        default=5,
        help="With --loop-until-empty: abort if the same file_path stays head of incomplete list "
        "this many times in a row. Use 0 to disable this guard (count-based guard still applies).",
    )
    ap.add_argument(
        "--max-no-progress",
        type=int,
        default=20,
        help="With --loop-until-empty: abort after this many iterations where the scoring-incomplete "
        "COUNT does not decrease (guards against no-op runs / ordering churn). Use 0 to disable.",
    )
    ap.add_argument("--dry-run", action="store_true", help="Print actions only; do not POST.")
    args = ap.parse_args()

    if args.loop_until_empty and not args.discover_scoring_incomplete:
        print("Error: --loop-until-empty requires --discover-scoring-incomplete", file=sys.stderr)
        return 2

    base = args.base_url.rstrip("/")
    if args.wsl_gateway:
        gw = _detect_wsl_default_gateway_webui(port=args.port)
        if gw:
            base = gw.rstrip("/")
            print(f"Using WSL gateway base URL: {base}", flush=True)
        else:
            print("Warning: --wsl-gateway set but could not read nameserver; using --base-url as-is.", flush=True)

    stages = [s.strip() for s in args.stages.split(",") if s.strip()]
    if not stages:
        print("Error: empty --stages", file=sys.stderr)
        return 2

    failures = 0

    if args.loop_until_empty:
        same_path_limit = int(args.max_same_path_retries)
        same_path_enabled = same_path_limit > 0
        no_progress_limit = int(args.max_no_progress)
        no_progress_enabled = no_progress_limit > 0
        print(
            f"[{_format_log_ts()}] Loop until no scoring-incomplete images; "
            f"max_runs={args.max_runs or 'unlimited'} "
            f"max_same_path_retries={same_path_limit if same_path_enabled else 'off'} "
            f"max_no_progress={no_progress_limit if no_progress_enabled else 'off'}",
            flush=True,
        )
        iteration = 0
        prev_fp: str | None = None
        same_streak = 0
        no_progress_streak = 0
        while True:
            if args.max_runs > 0 and iteration >= args.max_runs:
                print(f"[{_format_log_ts()}] Stopped: reached --max-runs {args.max_runs}", flush=True)
                break
            count_before: int | None = None
            if not args.dry_run:
                try:
                    count_before = _count_incomplete()
                except Exception as e:
                    print(
                        f"[{_format_log_ts()}] ERROR: could not count incomplete images ({type(e).__name__}): {e}",
                        file=sys.stderr,
                        flush=True,
                    )
                    return 1
            paths = _discover_scoring_incomplete_paths(1)
            if not paths:
                print(f"[{_format_log_ts()}] No more scoring-incomplete images.", flush=True)
                break
            fp = paths[0]
            if prev_fp is not None and fp == prev_fp:
                same_streak += 1
            else:
                same_streak = 0
            if same_path_enabled and same_streak >= same_path_limit:
                print(
                    f"[{_format_log_ts()}] Aborting: file_path still first incomplete after "
                    f"{same_streak} consecutive run(s): {fp}",
                    file=sys.stderr,
                    flush=True,
                )
                return 1
            iteration += 1
            ok, _jst = _process_one_file(
                base=base,
                fp=fp,
                idx=iteration,
                total=None,
                stages=stages,
                args=args,
            )
            if not ok:
                failures += 1
            if not args.dry_run and count_before is not None:
                try:
                    count_after = _count_incomplete()
                except Exception as e:
                    print(
                        f"[{_format_log_ts()}] ERROR: incomplete count after run ({type(e).__name__}): {e}",
                        file=sys.stderr,
                        flush=True,
                    )
                    return 1
                if count_after >= count_before:
                    no_progress_streak += 1
                    print(
                        f"[{_format_log_ts()}] Note: incomplete count still {count_after} "
                        f"(was {count_before}); no-progress streak {no_progress_streak}",
                        flush=True,
                    )
                    if no_progress_enabled and no_progress_streak >= no_progress_limit:
                        print(
                            f"[{_format_log_ts()}] Aborting: incomplete count did not decrease for "
                            f"{no_progress_streak} iteration(s) (last path {fp!r}).",
                            file=sys.stderr,
                            flush=True,
                        )
                        return 1
                else:
                    no_progress_streak = 0
            prev_fp = fp
        if failures:
            print(f"[{_format_log_ts()}] Loop ended with {failures} failure(s).", flush=True)
            return 1
        print(f"[{_format_log_ts()}] Loop ended (ok).", flush=True)
        return 0

    paths = list(iter_paths(args))
    if not paths:
        print("No paths to process.", file=sys.stderr)
        return 1

    print(f"[{_format_log_ts()}] Queued {len(paths)} path(s); stages={stages!r} run_mode={args.run_mode!r}", flush=True)

    for idx, raw_path in enumerate(paths, start=1):
        ok, _ = _process_one_file(
            base=base,
            fp=raw_path,
            idx=idx,
            total=len(paths),
            stages=stages,
            args=args,
        )
        if not ok:
            failures += 1

    if failures:
        print(f"[{_format_log_ts()}] Done with {failures} failure(s).", flush=True)
        return 1
    print(f"[{_format_log_ts()}] Done.", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nStopped by user.", flush=True)
        raise SystemExit(130) from None
