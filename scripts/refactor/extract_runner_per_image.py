#!/usr/bin/env python3
"""Extract per-item loop body from a runner _run_batch_internal into a helper method."""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def extract(
    rel_path: str,
    class_name: str,
    method_name: str,
    body_start: int,
    body_end: int,
    loop_var: str,
    loop_collection: str,
    done_log_pattern: str,
) -> None:
    path = ROOT / rel_path
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    body = "".join(lines[body_start - 1 : body_end])
    body = "\n".join(
        line[4:] if line.startswith("    ") else line
        for line in body.splitlines(keepends=True)
    )
    body = body.replace("continue\n", "return processed_count, skipped_count\n")

    method = f"""
    def {method_name}(
        self,
        {loop_var},
        *,
        skip_existing,
        job_id,
        report_collector,
        log,
        processed_count,
        skipped_count,
    ):
        \"\"\"Process one item in a batch run.\"\"\"
{body}
        return processed_count, skipped_count

"""

    insert_at = next(
        i for i, line in enumerate(lines) if line.startswith("    def _run_batch_internal")
    )

    loop_start = next(i for i, line in enumerate(lines) if line.strip() == f"for {loop_var} in {loop_collection}:")
    loop_end = next(
        i
        for i, line in enumerate(lines)
        if loop_start < i and done_log_pattern in line
    )

    loop_replacement = f"""        for {loop_var} in {loop_collection}:
            if self.stop_event.is_set():
                log("Stopped by user.", "WARNING")
                break
            if job_id and db.job_should_stop_processing(job_id):
                self.stop_event.set()
                log("Paused (job status).", "WARNING")
                break

            processed_count, skipped_count = self.{method_name}(
                {loop_var},
                skip_existing=skip_existing,
                job_id=job_id,
                report_collector=report_collector,
                log=log,
                processed_count=processed_count,
                skipped_count=skipped_count,
            )

"""

    # Preserve original stop messages by not replacing them - use original loop header only
    # Re-read original loop start lines for stop checks
    original_header = "".join(lines[loop_start:loop_start + 10])
    # Find where actual body starts after break checks
    header_end = loop_start
    for j in range(loop_start, loop_end):
        if lines[j].strip().startswith(f"self.current_count"):
            header_end = j
            break
    loop_header = "".join(lines[loop_start:header_end])

    loop_replacement = loop_header + f"""
            processed_count, skipped_count = self.{method_name}(
                {loop_var},
                skip_existing=skip_existing,
                job_id=job_id,
                report_collector=report_collector,
                log=log,
                processed_count=processed_count,
                skipped_count=skipped_count,
            )

"""

    new_lines = (
        lines[:insert_at]
        + [method]
        + lines[insert_at:loop_start]
        + [loop_replacement]
        + lines[loop_end:]
    )
    path.write_text("".join(new_lines), encoding="utf-8")
    print(f"extracted {method_name} in {rel_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", choices=["metadata", "indexing"])
    args = parser.parse_args()
    if args.target == "metadata":
        extract(
            "modules/metadata_runner.py",
            "MetadataRunner",
            "_process_metadata_image_row",
            210,
            384,
            "row",
            "all_images",
            "Done. Processed:",
        )
    elif args.target == "indexing":
        extract(
            "modules/indexing_runner.py",
            "IndexingRunner",
            "_process_indexing_file",
            576,
            819,
            "file_path",
            "all_files",
            "Done. Processed:",
        )


if __name__ == "__main__":
    main()
