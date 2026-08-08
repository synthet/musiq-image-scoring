"""Cold/warm latency benchmark scaffold for student vs ensemble."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Callable

from scripts.research.student_scorer.common import write_json


def time_call(fn: Callable[[], Any], *, warmup: int = 1, reps: int = 5) -> dict[str, float]:
    for _ in range(warmup):
        fn()
    samples = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - t0)
    samples.sort()
    return {
        "median_s": samples[len(samples) // 2],
        "p95_s": samples[min(len(samples) - 1, int(0.95 * (len(samples) - 1)))],
        "mean_s": sum(samples) / len(samples),
        "reps": float(reps),
    }


def benchmark_report(
    *,
    student_infer_s: dict[str, float],
    ensemble_infer_s: dict[str, float] | None = None,
    checkpoint_size_mb: float | None = None,
) -> dict[str, Any]:
    speedup = None
    if ensemble_infer_s and student_infer_s.get("median_s"):
        if student_infer_s["median_s"] > 0:
            speedup = ensemble_infer_s["median_s"] / student_infer_s["median_s"]
    return {
        "student": student_infer_s,
        "ensemble": ensemble_infer_s,
        "speedup_median": speedup,
        "checkpoint_size_mb": checkpoint_size_mb,
        "note": "End-to-end path should include RAW prep + DB persist separately",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Student inference benchmark scaffold")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--student-median-s", type=float, default=0.05)
    parser.add_argument("--ensemble-median-s", type=float, default=0.40)
    args = parser.parse_args(argv)
    report = benchmark_report(
        student_infer_s={"median_s": args.student_median_s, "p95_s": args.student_median_s * 1.2, "mean_s": args.student_median_s, "reps": 1},
        ensemble_infer_s={"median_s": args.ensemble_median_s, "p95_s": args.ensemble_median_s * 1.2, "mean_s": args.ensemble_median_s, "reps": 1},
    )
    write_json(args.out, report)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
