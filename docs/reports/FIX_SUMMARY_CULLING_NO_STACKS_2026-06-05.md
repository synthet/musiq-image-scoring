# Summary of Work: Culling "No Stacks" Bug Fix

## Issue Description
Users reported that newly processed folders were completing the culling phase but failing to generate any stacks (`stack_id` remained null for all images).

## Root Cause Analysis
The investigation revealed a phase-status ownership conflict between `SelectionRunner` and `ClusteringEngine`:

1.  **Redundant Updates**: `SelectionRunner` was manually setting images to `PhaseStatus.RUNNING` before calling `SelectionService`.
2.  **Engine Skipping**: `ClusteringEngine` (called by the service) uses `explain_phase_run_decision` to determine which images to process. It correctly identifies `RUNNING` status as "already in progress" and skips those images to avoid race conditions.
3.  **Zero Stacks**: Because the engine skipped all images in the folder, it finished without creating any stacks, then marked the "stuck" `RUNNING` rows as `DONE` as part of its cleanup logic.

## Resolution
Modified `modules/selection_runner.py` to remove premature status transitions.

- **Removed**: `db.set_image_phase_status(..., PhaseStatus.RUNNING)` before the run.
- **Removed**: `db.set_image_phase_status(..., PhaseStatus.DONE)` after the run.
- **Result**: `ClusteringEngine` now has full ownership of the image lifecycle during the culling phase, ensuring it sees images as runnable and processes them into stacks.

## Verification
- **Reproduction**: A custom script confirmed that pre-marking images as `RUNNING` caused the engine to skip the folder with `runnable_rows=0`.
- **Validation**: After the fix, the same script verified that `SelectionRunner` no longer interferes with the status, and the engine correctly processes the images.
- **Regression Check**: Other runners (`Scoring`, `Tagging`) were checked and do not exhibit this premature status-setting behavior.

## Files Modified
- `modules/selection_runner.py`
- `CHANGELOG.md`
