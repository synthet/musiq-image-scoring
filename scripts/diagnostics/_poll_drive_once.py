"""One-shot multi-poll helper for drive monitoring (used by agents)."""
from __future__ import annotations

import json
import sys
import time
import urllib.request


def main() -> int:
    polls = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    interval = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
    base = sys.argv[3] if len(sys.argv) > 3 else "http://127.0.0.1:7860"

    for i in range(polls):
        try:
            with urllib.request.urlopen(f"{base.rstrip('/')}/api/runs/drive/status", timeout=30) as r:
                d = json.loads(r.read().decode())
        except Exception as exc:
            print(f"poll {i + 1} error: {exc}", file=sys.stderr)
            return 2

        st = d.get("state") or {}
        out = d.get("outstanding") or {}
        lr = st.get("last_result") or {}
        h = lr.get("health") or out.get("health") or {}
        print(f"--- poll {i + 1} @ {time.strftime('%H:%M:%S')} ---")
        print(f"  driving={st.get('enabled')} stop_reason={st.get('stop_reason')}")
        print(
            f"  outstanding={out.get('total_outstanding')} "
            f"in_flight={h.get('in_flight_folders')} "
            f"schedulable={h.get('schedulable_folders')} "
            f"blocked={h.get('blocked_folders')}"
        )
        if lr:
            print(
                f"  last_tick={lr.get('last_tick_reason')} "
                f"queued={lr.get('scheduled')} skipped={lr.get('skipped')} "
                f"loop_detected={lr.get('loop_detected')}"
            )
        bc = out.get("bucket_counts") or lr.get("bucket_counts") or {}
        if bc:
            top = sorted(bc.items(), key=lambda x: -x[1])[:5]
            parts = [f"{k}={v}" for k, v in top]
            print(f"  buckets: {', '.join(parts)}")
        if not st.get("enabled"):
            print("  drive stopped")
            return 0
        if i < polls - 1:
            time.sleep(interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
