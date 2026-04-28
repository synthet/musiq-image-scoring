# Code Review and Design Review (2026-02-09)

## Scope

Reviewed core runtime and persistence paths focused on:

- `modules/scoring.py`
- `modules/pipeline.py`
- `modules/engine.py`
- `modules/db.py`
- `modules/ui/state.py`

## Executive Summary

The project has a strong functional base (clear worker separation in pipeline stages and explicit job objects), but there are several maintainability and reliability risks in hot paths. The most important issues are duplicated class initialization code, debug-print leakage in database connection setup, and broad exception swallowing that can mask data and runtime failures.

## Code Review Findings

### 1) Duplicate constructor definition in `ScoringRunner` (Medium)

`ScoringRunner` defines `__init__` twice. The first definition is overwritten by the second one at class load time. This is not immediately fatal, but it is error-prone and makes future edits risky because only the second initializer is active.

**Evidence:** `modules/scoring.py` contains two consecutive `def __init__(self):` blocks in the same class.

**Recommendation:** Remove the first constructor and keep a single authoritative initializer.

---

### 2) Debug prints and sensitive operational details in DB connection path (High)

`get_db()` uses multiple `print(...)` debug statements, including connection diagnostics and DSN messages in runtime paths. This can pollute logs, leak environment topology, and make service output noisy in production runs.

**Evidence:** `modules/db.py` prints WSL diagnostics and connection debug values (`connect function`, `dsn`, `conn`).

**Recommendation:** Replace with structured logging at debug level and gate with a debug flag; avoid printing connection object details.

---

### 3) Broad exception swallowing in worker and DB code paths (High)

Several places use `except:` or `except Exception` with minimal/no remediation and sometimes silent `pass`, including cleanup and GPU cache cleanup. This makes root-cause analysis harder and can hide persistent failures.

**Evidence:** `modules/pipeline.py` has multiple `except: pass` blocks (cleanup and cache clear); `modules/db.py` uses broad catch blocks around driver configuration and path resolution.

**Recommendation:** Narrow exception types where possible and log context-rich warning messages instead of silent passes.

---

### 4) Per-image converter instantiation for RAW prep may be costly (Medium)

RAW conversion in `PrepWorker` creates a fresh `MultiModelMUSIQ(skip_gpu=True)` object per RAW image. Even if "lightweight," object construction in a tight path can be expensive and can become a throughput bottleneck for large RAW batches.

**Evidence:** `modules/pipeline.py` instantiates `MultiModelMUSIQ(skip_gpu=True)` inside `PrepWorker.process` for each RAW item.

**Recommendation:** Extract RAW conversion into a dedicated lightweight converter utility (or long-lived worker-local converter instance).

---

### 5) Unused/placeholder typed state object increases drift risk (Low)

`AppState` is documented as currently unused. Keeping unused state abstractions around can drift from actual app behavior and mislead maintainers.

**Evidence:** `modules/ui/state.py` docstring explicitly states `AppState` is currently unused.

**Recommendation:** Either wire this into app state creation or remove/relocate as future-design note.

## Design Review

### Strengths

- **Pipeline stage separation is clear:** prep, scoring, and result phases are explicit and understandable.
- **Job DTO (`ImageJob`) is pragmatic:** carries status, metadata, and temporary resources across stages.
- **Backfill strategy in prep stage is thoughtful:** avoids redundant model recomputation when partial scores already exist.

### Design Risks

1. **High coupling across layers**
   - Pipeline workers directly call DB and metadata side effects, reducing testability and making error boundaries blurry.
   - Suggestion: introduce service interfaces (`ScoreRepository`, `MetadataWriter`) passed into workers.

2. **Monolithic DB module responsibilities**
   - `modules/db.py` handles platform detection, WSL translation, process orchestration, query translation, and connection proxying.
   - Suggestion: split into `db/connection.py`, `db/sql_translate.py`, `db/repository.py` for clearer ownership and easier tests.

3. **Operational concerns mixed with core logic**
   - Auto-start behavior and environment-specific fallback logic inside normal DB open path can surprise callers.
   - Suggestion: make startup behavior explicit with a feature flag and central startup initialization step.

## Suggested Remediation Plan

1. **Stabilization (short-term):**
   - Remove duplicate `ScoringRunner.__init__`.
   - Replace `print` diagnostics in DB with logger calls.
   - Remove silent `except: pass` where possible.

2. **Reliability (mid-term):**
   - Move RAW conversion helper to worker-local reusable instance.
   - Add structured error classes for prep/scoring/result stages.

3. **Architecture (long-term):**
   - Decouple worker side effects via interfaces.
   - Split DB module by responsibility and add focused unit tests around SQL translation and connection behavior.
