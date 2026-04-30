#!/usr/bin/env python3
"""
Continuously heal bird species workflow until no eligible work remains.

The script repeatedly:
1) Calls POST /api/maintenance/heal/bird_species with budget=1.
2) Waits while /api/bird-species/status reports the runner is active.
3) Repeats until heal reports zero eligible folders and no in-flight work.

Examples:
  # Preview only (no scheduling, no waiting)
  python scripts/maintenance/heal_bird_species_until_done.py --dry-run

  # Execute with default behavior
  python scripts/maintenance/heal_bird_species_until_done.py

  # Execute with explicit safety caps
  python scripts/maintenance/heal_bird_species_until_done.py --max-cycles 300 --max-wait-seconds 1800
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


LOG = logging.getLogger("heal_bird_species_until_done")


def _request_json(
    method: str,
    url: str,
    *,
    payload: Optional[Dict[str, Any]] = None,
    timeout: int = 30,
    retries: int = 6,
    base_retry_delay: float = 1.0,
    max_retry_delay: float = 60.0,
    retry_jitter: float = 0.25,
) -> Dict[str, Any]:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    last_err: Optional[Exception] = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw)
        except urllib.error.HTTPError as err:
            last_err = err
            if attempt >= retries:
                break
            status = int(err.code or 0)
            if status in (408, 425, 429) or status >= 500:
                retry_after_header = err.headers.get("Retry-After") if err.headers else None
                retry_after = None
                if retry_after_header:
                    try:
                        retry_after = float(retry_after_header)
                    except ValueError:
                        retry_after = None
                exp_delay = min(max_retry_delay, base_retry_delay * (2 ** attempt))
                jitter_multiplier = max(0.0, 1.0 + random.uniform(-retry_jitter, retry_jitter))
                sleep_for = max(retry_after or 0.0, exp_delay * jitter_multiplier)
                LOG.warning(
                    "HTTP %s from %s %s; retrying in %.1fs (%s/%s)",
                    status,
                    method.upper(),
                    url,
                    sleep_for,
                    attempt + 1,
                    retries,
                )
                time.sleep(sleep_for)
                continue
            break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as err:
            last_err = err
            if attempt >= retries:
                break
            exp_delay = min(max_retry_delay, base_retry_delay * (2 ** attempt))
            jitter_multiplier = max(0.0, 1.0 + random.uniform(-retry_jitter, retry_jitter))
            sleep_for = exp_delay * jitter_multiplier
            LOG.warning(
                "Request failed (%s %s): %s; retrying in %.1fs (%s/%s)",
                method.upper(),
                url,
                err,
                sleep_for,
                attempt + 1,
                retries,
            )
            time.sleep(sleep_for)
    raise RuntimeError(f"Request failed after retries: {method.upper()} {url}: {last_err}")


def call_heal(
    base_url: str,
    *,
    run_mode: str,
    dry_run: bool,
    root_path: Optional[str],
    request_timeout: int,
) -> Dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/maintenance/heal/bird_species"
    payload: Dict[str, Any] = {
        "dry_run": dry_run,
        "budget": 1,
        "run_mode": run_mode,
    }
    if root_path:
        payload["root_path"] = root_path
    return _request_json("POST", url, payload=payload, timeout=request_timeout)


def get_bird_status(base_url: str, *, request_timeout: int) -> Dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/bird-species/status"
    return _request_json("GET", url, timeout=request_timeout)


def wait_for_bird_runner_idle(
    base_url: str,
    *,
    poll_seconds: float,
    request_timeout: int,
    max_wait_seconds: int,
) -> bool:
    start = time.time()
    first = True
    while True:
        status = get_bird_status(base_url, request_timeout=request_timeout)
        data = status.get("data") or {}
        is_running = bool(data.get("is_running"))
        cur = data.get("current")
        total = data.get("total")
        msg = str(data.get("status_message") or "")

        if not is_running:
            if not first:
                LOG.info("Bird species runner is idle.")
            return True

        elapsed = int(time.time() - start)
        LOG.info("Waiting: runner active current=%s total=%s status=%s elapsed=%ss", cur, total, msg, elapsed)
        first = False

        if max_wait_seconds > 0 and elapsed >= max_wait_seconds:
            LOG.error("Wait timeout reached (%ss) while bird species runner is still active.", max_wait_seconds)
            return False

        time.sleep(max(0.2, poll_seconds))


def run(args: argparse.Namespace) -> int:
    total_scheduled = 0
    last_heal_call_at: Optional[float] = None
    for cycle in range(1, args.max_cycles + 1):
        if last_heal_call_at is not None and args.cycle_delay_seconds > 0:
            elapsed_since_heal = time.time() - last_heal_call_at
            debounce_sleep = args.cycle_delay_seconds - elapsed_since_heal
            if debounce_sleep > 0:
                LOG.debug("Debounce: sleeping %.2fs before next heal cycle.", debounce_sleep)
                time.sleep(debounce_sleep)

        heal_resp = call_heal(
            args.base_url,
            run_mode=args.run_mode,
            dry_run=args.dry_run,
            root_path=args.root_path,
            request_timeout=args.request_timeout,
        )
        last_heal_call_at = time.time()
        if not bool(heal_resp.get("success")):
            LOG.error("Heal API returned non-success: %s", heal_resp)
            return 1

        data = heal_resp.get("data") or {}
        scheduled = data.get("scheduled") or []
        scheduled_count = len(scheduled) if isinstance(scheduled, list) else int(scheduled or 0)
        eligible = int(data.get("eligible_folders") or 0)
        needing = int(data.get("folders_needing_work") or 0)
        total_scheduled += scheduled_count

        LOG.info(
            "Cycle %s: scheduled=%s eligible=%s needing=%s dry_run=%s",
            cycle,
            scheduled_count,
            eligible,
            needing,
            args.dry_run,
        )

        if args.dry_run:
            if scheduled_count == 0 and eligible == 0:
                LOG.info("Dry-run indicates no remaining eligible bird-species healing work.")
                LOG.info("Done: cycles=%s total_scheduled=%s", cycle, total_scheduled)
                return 0
            if cycle >= args.max_cycles:
                LOG.info(
                    "Dry-run reached --max-cycles=%s; stopping without scheduling.",
                    args.max_cycles,
                )
                LOG.info("Done: cycles=%s total_scheduled=%s", cycle, total_scheduled)
                return 0
            continue

        if scheduled_count > 0:
            ok = wait_for_bird_runner_idle(
                args.base_url,
                poll_seconds=args.poll_seconds,
                request_timeout=args.request_timeout,
                max_wait_seconds=args.max_wait_seconds,
            )
            if not ok:
                return 2
            continue

        # No schedule this cycle. Confirm runner is idle before declaring completion.
        status = get_bird_status(args.base_url, request_timeout=args.request_timeout)
        is_running = bool((status.get("data") or {}).get("is_running"))
        if eligible == 0 and not is_running:
            LOG.info("No eligible folders remain and runner is idle.")
            LOG.info("Done: cycles=%s total_scheduled=%s", cycle, total_scheduled)
            return 0

        if is_running:
            LOG.info("No new folder scheduled this cycle, but runner is still active; waiting.")
            ok = wait_for_bird_runner_idle(
                args.base_url,
                poll_seconds=args.poll_seconds,
                request_timeout=args.request_timeout,
                max_wait_seconds=args.max_wait_seconds,
            )
            if not ok:
                return 2

    LOG.error("Hit --max-cycles=%s before completion.", args.max_cycles)
    return 3


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-url", default="http://127.0.0.1:7860", help="API base URL.")
    p.add_argument("--root-path", default=None, help="Optional path scope passed to heal API.")
    p.add_argument("--run-mode", default="validate_and_repair", help="Heal run_mode.")
    p.add_argument("--dry-run", action="store_true", help="Do not enqueue; only inspect heal candidates.")
    p.add_argument("--poll-seconds", type=float, default=2.0, help="Status polling interval while waiting.")
    p.add_argument(
        "--cycle-delay-seconds",
        type=float,
        default=2.0,
        help="Minimum delay between heal scheduling calls (debounce).",
    )
    p.add_argument(
        "--max-cycles",
        type=int,
        default=1000,
        help="Maximum heal cycles before exiting with error.",
    )
    p.add_argument(
        "--max-wait-seconds",
        type=int,
        default=0,
        help="Max seconds to wait for runner idle per wait phase (0 disables timeout).",
    )
    p.add_argument("--request-timeout", type=int, default=30, help="Per-request timeout seconds.")
    p.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    if args.max_cycles < 1:
        LOG.error("--max-cycles must be >= 1")
        return 2
    if args.poll_seconds <= 0:
        LOG.error("--poll-seconds must be > 0")
        return 2
    if args.cycle_delay_seconds < 0:
        LOG.error("--cycle-delay-seconds must be >= 0")
        return 2
    if args.request_timeout < 1:
        LOG.error("--request-timeout must be >= 1")
        return 2
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
