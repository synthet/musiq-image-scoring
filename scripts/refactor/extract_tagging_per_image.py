#!/usr/bin/env python3
"""Extract TaggingRunner per-image loop body into _process_tagging_image_row."""

from pathlib import Path

PATH = Path(__file__).resolve().parents[2] / "modules" / "tagging.py"
lines = PATH.read_text(encoding="utf-8").splitlines(keepends=True)

# 1-based line numbers from original _run_batch_internal loop body
BODY_START = 721
BODY_END = 992

body = "".join(lines[BODY_START - 1 : BODY_END])
body = "\n".join(
    line[4:] if line.startswith("    ") else line
    for line in body.splitlines(keepends=True)
)

method = f'''
    def _process_tagging_image_row(
        self,
        row,
        *,
        custom_keywords,
        overwrite,
        generate_captions,
        generate_accessibility,
        job_id,
        report_collector,
        write_keyword_relevance,
        log,
        processed_count,
        skipped_count,
        processed_folders,
    ):
        """Process a single image row during batch tagging."""
{body}

        return processed_count, skipped_count

'''

loop_replacement = """        for row in all_images:
            if self.stop_event.is_set():
                log("Tagging stopped by user.", "WARNING")
                break
            if job_id and db.job_should_stop_processing(job_id):
                self.stop_event.set()
                log("Tagging paused (job status).", "WARNING")
                break

            processed_count, skipped_count = self._process_tagging_image_row(
                row,
                custom_keywords=custom_keywords,
                overwrite=overwrite,
                generate_captions=generate_captions,
                generate_accessibility=generate_accessibility,
                job_id=job_id,
                report_collector=report_collector,
                write_keyword_relevance=write_keyword_relevance,
                log=log,
                processed_count=processed_count,
                skipped_count=skipped_count,
                processed_folders=processed_folders,
            )

"""

# Insert method before _run_batch_internal
insert_at = None
for i, line in enumerate(lines):
    if line.startswith("    def _run_batch_internal"):
        insert_at = i
        break
if insert_at is None:
    raise SystemExit("_run_batch_internal not found")

# Replace loop block
loop_start = None
loop_end = None
for i, line in enumerate(lines):
    if loop_start is None and line.strip() == "for row in all_images:":
        loop_start = i
    if loop_start is not None and line.strip().startswith("log(f\"Done. Processed:"):
        loop_end = i
        break

if loop_start is None or loop_end is None:
    raise SystemExit("loop block not found")

new_lines = (
    lines[:insert_at]
    + [method]
    + lines[insert_at:loop_start]
    + [loop_replacement]
    + lines[loop_end:]
)

PATH.write_text("".join(new_lines), encoding="utf-8")
print("extracted _process_tagging_image_row")
