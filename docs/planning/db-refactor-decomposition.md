# DB.py God Object Refactoring Plan

**Document:** DB.py Decomposition Strategy  
**Status:** Planning (Not Yet Implemented)  
**Priority:** Medium (Post-MVP)  
**Severity:** Medium – High defect risk, merge conflicts, testing difficulty  
**Last Updated:** 2026-06-30  

**Related:** Phased execution checklist — [CODEBASE_SIZE_REFACTOR_PLAN.md](refactoring/CODEBASE_SIZE_REFACTOR_PLAN.md) (Phase 2). Source audit — [CODEBASE_SIZE_AUDIT_2026-06.md](../reports/CODEBASE_SIZE_AUDIT_2026-06.md).

---

## Executive Summary

`modules/db.py` has grown to **414 KB / 10,565 lines**, consolidating 60+ public methods across 8+ distinct domains:
- Connection management & routing
- SQL translation (Firebird ↔ PostgreSQL)
- Image CRUD & querying
- Folder & stack operations
- Job lifecycle & phases
- Keywords (normalized schema)
- Embeddings
- Backup & telemetry

This god object creates high defect risk, merge conflict hotspots, difficult testing, and reduced code reusability. This plan proposes a phased decomposition into domain-specific modules.

---

## Problem Statement

### Current State: `modules/db.py`

| Metric | Value |
|--------|-------|
| File size | 414 KB |
| Lines of code | ~10,565 |
| Public functions | 60+ |
| Private functions | 40+ |
| Imports from db.py | 90+ locations |
| Circular dependencies | 3–5 (via db_connector, pipeline, etc.) |

### Risks

1. **Defect Impact Radius:** Any change to this file risks breaking unrelated functionality.
2. **Merge Conflicts:** High churn on a single file → daily merge battles in multi-developer workflows.
3. **Testing Difficulty:** Hard to test a single concern in isolation; tests often drag in full DB initialization.
4. **LLM Context Window:** File exceeds LLM context limits, making AI-assisted maintenance unreliable.
5. **Code Reusability:** Tightly coupled functions prevent reuse in alternative contexts (CLI tools, batch jobs).
6. **Onboarding:** New developers struggle to find/understand related functions scattered across 10k lines.

---

## Proposed Architecture

### Domain Decomposition

```
modules/
├── db.py                          ← Reduced to ~2,000 LOC
│   ├── __init__.py               (re-exports public API for backward compat)
│   ├── connection.py             (NEW: 200 LOC)
│   ├── images.py                 (NEW: 1,500 LOC)
│   ├── folders.py                (NEW: 800 LOC)
│   ├── stacks.py                 (NEW: 600 LOC)
│   ├── jobs.py                   (NEW: 2,000 LOC) [already exists: db/jobs.py]
│   ├── keywords.py               (NEW: 800 LOC)
│   ├── embeddings.py             (NEW: 600 LOC)
│   ├── telemetry.py              (NEW: 400 LOC)
│   └── backup.py                 (NEW: 300 LOC)
│
└── db_connector/
    ├── __init__.py              (existing)
    ├── protocol.py              (existing)
    └── factory.py               (existing)
```

### New Module Responsibilities

#### `db/connection.py` (~200 LOC)
- `get_db()`, `connection()` context manager
- Engine routing (`_get_db_engine()`)
- Connection pool management
- PostgreSQL/Firebird proxy wrappers
- Transaction helpers (`_tx()` context manager)

**Exports:**
```python
def get_db() -> Connection
def connection() -> AsyncContextManager
def get_connector() -> IConnector
```

---

#### `db/images.py` (~1,500 LOC)
- Image CRUD: `get_image_details()`, `create_image()`, `update_image_field()`
- Image queries: `get_images()`, `find_images_by_hash()`, `get_image_by_uuid()`
- Image filtering & selection: `apply_selectors()`, `filter_images()`
- Image metadata: `update_image_metadata()`, `sync_image_xmp()`
- Image deletion & cleanup: `delete_image()`, `remove_stale_images()`
- Caching: `get_all_paths()`, `get_resolved_path()`
- Batch operations: `bulk_update_images()`, `get_incomplete_records()`

**Exports:**
```python
def get_image_details(file_path: str) -> dict | None
def get_images(query: str, limit=100) -> list[dict]
def update_image_metadata(file_path, keywords, title, desc, rating, label) -> bool
def get_image_phase_statuses(image_id: int) -> dict
# ... 30+ public functions
```

**Dependencies:**
- `db.connection` (for transactions)
- `db.keywords` (for keyword operations)

---

#### `db/folders.py` (~800 LOC)
- Folder CRUD: `get_folder()`, `create_folder()`, `update_folder()`
- Folder queries: `get_folders()`, `get_folder_contents()`
- Folder phase status: `get_folder_phase_summary()`, `get_folder_phase_statuses()`
- Folder tree: `get_folder_tree()`, `list_folder_descendants()`
- Folder cleanup: `delete_folder()`, `remove_empty_folders()`
- Sync: `sync_folder_to_db()`, `detect_orphaned_folders()`

**Exports:**
```python
def get_folder(path: str) -> dict | None
def create_folder(path: str) -> int
def get_folder_phase_summary(path: str) -> dict
def get_folder_tree(root_path: str) -> list[dict]
# ... 15+ public functions
```

**Dependencies:**
- `db.connection`
- `db.images` (for image counts in folders)

---

#### `db/stacks.py` (~600 LOC)
- Stack CRUD: `create_stack()`, `get_stack()`, `delete_stack()`
- Stack membership: `add_image_to_stack()`, `remove_image_from_stack()`
- Stack queries: `get_stacks()`, `get_stack_images()`, `find_stack_for_image()`
- Stack cleanup: `delete_empty_stacks()`, `reconcile_stacks()`

**Exports:**
```python
def create_stack(name: str, folder_id: int, image_ids: list[int]) -> int
def get_stacks(folder_id: int = None) -> list[dict]
def get_stack_images(stack_id: int) -> list[dict]
# ... 12+ public functions
```

**Dependencies:**
- `db.connection`
- `db.images`

---

#### `db/jobs.py` (EXTEND EXISTING: ~2,000 LOC total)
**Note:** `modules/db/jobs.py` already exists. Extend & consolidate:

- Job CRUD: `create_job()`, `get_job_by_id()`, `update_job_status()`
- Job queries: `get_jobs()`, `get_job_phases()`, `get_next_pending_job_phase()`
- Job lifecycle: `enqueue_job()`, `dequeue_job()`, `cancel_job()`, `request_cancel_job()`
- Job phases: `set_job_phase_state()`, `set_image_phase_status()`, `get_image_phase_statuses()`
- Recovery: `recover_interrupted_jobs()`, `list_stale_running_image_phase_rows()`
- Job state machine: `JOB_ALLOWED_TRANSITIONS`, `JOB_TERMINAL_STATES`

**Exports:**
```python
def create_job(input_path: str, job_type: str = None, status: str = "pending") -> int
def get_job_by_id(job_id: int) -> dict | None
def update_job_status(job_id: int, status: str, log: str = None) -> bool
def set_job_phase_state(job_id: int, phase_code: str, state: str, error_message: str = None) -> bool
# ... 25+ public functions
```

**Dependencies:**
- `db.connection`
- `db.images` (for phase status queries)
- `db.folders` (for folder lookups)

---

#### `db/keywords.py` (~800 LOC)
- Keyword CRUD: `add_keyword()`, `remove_keyword()`, `get_keywords()`
- Image keywords: `_sync_image_keywords()`, `update_image_keywords()`
- Keyword queries: `get_all_keywords()`, `search_keywords()`, `get_keyword_stats()`
- Keyword filtering: `_add_keyword_filter()`, `filter_images_by_keyword()`
- Deprecation helpers: `_get_keywords_from_images_table()` (Firebird compat)

**Exports:**
```python
def add_keyword(image_id: int, keyword: str) -> bool
def get_keywords(image_id: int) -> list[str]
def update_image_keywords(image_id: int, keywords_csv: str) -> bool
def filter_images_by_keyword(keyword: str, folder_id: int = None) -> list[int]
# ... 18+ public functions
```

**Dependencies:**
- `db.connection`
- `db.images`

---

#### `db/embeddings.py` (~600 LOC)
- Embedding storage: `store_embedding()`, `get_embedding()`, `update_embedding()`
- Embedding queries: `get_images_with_embeddings()`, `find_similar_embeddings()`
- Embedding indexes: `create_embedding_index()`, `rebuild_embeddings()`
- Embedding cleanup: `remove_stale_embeddings()`, `validate_embedding_integrity()`

**Exports:**
```python
def store_embedding(image_id: int, embedding: np.ndarray, space: str = "default") -> bool
def get_embedding(image_id: int, space: str = "default") -> np.ndarray | None
def find_similar_embeddings(embedding: np.ndarray, limit: int = 10) -> list[int]
# ... 10+ public functions
```

**Dependencies:**
- `db.connection`
- `db.images`

---

#### `db/telemetry.py` (~400 LOC)
- Pipeline events: `record_pipeline_event()`, `get_pipeline_events()`
- Job telemetry: `record_job_telemetry()`, `get_job_telemetry()`
- Performance metrics: `compute_phase_metrics()`, `get_performance_summary()`
- Logging: `log_phase_change()`, `log_job_transition()`

**Exports:**
```python
def record_pipeline_event(event_type: str, severity: str, message: str, context: dict = None) -> bool
def get_pipeline_events(limit: int = 100, hours_back: int = 24) -> list[dict]
def get_performance_summary(days: int = 7) -> dict
# ... 12+ public functions
```

**Dependencies:**
- `db.connection`
- `db.jobs`

---

#### `db/backup.py` (~300 LOC)
- Backup operations: `backup_database()`, `restore_backup()`, `list_backups()`
- Backup validation: `validate_backup()`, `estimate_backup_size()`
- Incremental sync: `sync_to_firebird()` (for Electron compat during Phase 4)

**Exports:**
```python
def backup_database(destination: str = None) -> dict
def restore_backup(backup_file: str, dry_run: bool = False) -> bool
def list_backups() -> list[dict]
# ... 8+ public functions
```

**Dependencies:**
- `db.connection`

---

### Backward Compatibility Layer

#### `modules/db.py` (Refactored to ~2,000 LOC)

Keep as a **facade** re-exporting all public functions from submodules:

```python
"""
Database abstraction layer (legacy facade).

DEPRECATED: This module is now a facade over domain-specific submodules.
Direct imports are discouraged; import from specific submodules instead:

  from modules.db.images import get_image_details
  from modules.db.folders import get_folder
  from modules.db.jobs import create_job

Legacy imports still work for backward compatibility:

  from modules.db import get_image_details, get_folder, create_job
"""

# Re-export all public functions (100+ total) from submodules
from .connection import get_db, connection, get_connector
from .images import (
    get_image_details,
    get_images,
    update_image_metadata,
    # ... 30+ functions
)
from .folders import (
    get_folder,
    create_folder,
    # ... 15+ functions
)
from .jobs import (
    create_job,
    update_job_status,
    # ... 25+ functions
)
# ... etc for all submodules

# Keep helper constants and enums in db.py
JOB_TERMINAL_STATES = {"completed", "failed", "cancelled", "interrupted"}
JOB_ALLOWED_TRANSITIONS = { ... }

__all__ = [
    # Connection
    "get_db", "connection", "get_connector",
    # Images
    "get_image_details", "get_images", "update_image_metadata",
    # ... 100+ total
]
```

**Benefits:**
- Zero breaking changes to 90+ import sites
- Gradual migration path
- Clear deprecation warnings guiding new code

---

## Migration Strategy

### Phase 1: Foundation (Weeks 1–2)

**Objective:** Extract non-dependent modules

1. Create `modules/db/` package with `__init__.py`
2. Extract `db/connection.py` (200 LOC)
   - Move: `get_db()`, `connection()`, `get_connector()`, proxies, engine routing
   - Update imports in `db.py`
3. Extract `db/telemetry.py` (400 LOC)
   - Move: All telemetry/logging functions
   - No dependencies on other DB modules
4. Update `modules/db.py` to re-export from new modules
5. Run full test suite; verify zero breaking changes

**Deliverable:**
- `modules/db/connection.py` ✅
- `modules/db/telemetry.py` ✅
- `modules/db/__init__.py` with re-exports
- All tests passing

---

### Phase 2: Core Domains (Weeks 3–6)

**Objective:** Extract core data model modules (images, folders, stacks, keywords)

1. Extract `db/images.py` (1,500 LOC)
   - Dependency: `db.connection`, `db.keywords`
   - Test in isolation with mock connector
2. Extract `db/folders.py` (800 LOC)
   - Dependency: `db.connection`, `db.images`
   - Test folder queries independently
3. Extract `db/stacks.py` (600 LOC)
   - Dependency: `db.connection`, `db.images`
4. Extract `db/keywords.py` (800 LOC)
   - Dependency: `db.connection`, `db.images`
5. Update `modules/db.py` re-exports
6. Full regression testing

**Deliverable:**
- `modules/db/{images,folders,stacks,keywords}.py` ✅
- All import sites still working
- 90% reduction in `db.py` size

---

### Phase 3: Job Lifecycle (Weeks 7–8)

**Objective:** Consolidate & extend existing job module

1. Consolidate `modules/db/jobs.py` (extend existing)
   - Move remaining job-related code from `db.py`
   - Unify job phase state machine
   - Add recovery functions: `recover_interrupted_jobs()`, `list_stale_running_image_phase_rows()`
2. Test job state transitions thoroughly
3. Update `modules/db.py` re-exports

**Deliverable:**
- Unified `modules/db/jobs.py` (2,000 LOC) ✅
- State machine unit tests

---

### Phase 4: Specialized Domains (Weeks 9–10)

**Objective:** Extract embeddings and backup modules

1. Extract `db/embeddings.py` (600 LOC)
   - Dependency: `db.connection`, `db.images`
2. Extract `db/backup.py` (300 LOC)
   - Dependency: `db.connection`
3. Final refactor of `modules/db.py` → facade only (~2,000 LOC)
4. Comprehensive testing

**Deliverable:**
- `modules/db/{embeddings,backup}.py` ✅
- `modules/db.py` reduced to ~2,000 LOC (95% reduction)
- Full API backward-compatible

---

### Phase 5: Documentation & Cleanup (Week 11)

**Objective:** Finalize and document

1. Add `@deprecated` warnings to `modules/db.py` public functions
   ```python
   def get_image_details(...):
       """DEPRECATED: Import from modules.db.images instead."""
       warnings.warn("...", DeprecationWarning)
       return db_images.get_image_details(...)
   ```
2. Create module docstrings with examples
3. Update CLAUDE.md to recommend new import patterns
4. Create `docs/DB_MODULE_MIGRATION.md` migration guide
5. Final validation: all tests pass, no performance regression

**Deliverable:**
- Complete decomposition ✅
- Migration guide for developers
- Deprecation warnings in place

---

## Testing Strategy

### Per-Module Testing

Each new module should have dedicated unit tests:

```
tests/
├── test_db_connection.py         (connection management)
├── test_db_images.py             (CRUD, queries, filtering)
├── test_db_folders.py            (folder operations, hierarchy)
├── test_db_stacks.py             (stack membership)
├── test_db_jobs.py               (job state machine, recovery) [extend existing]
├── test_db_keywords.py           (keyword sync, filtering)
├── test_db_embeddings.py         (storage, similarity search)
├── test_db_telemetry.py          (event logging)
├── test_db_backup.py             (backup/restore)
└── test_db_compat.py             (backward compat via facade)
```

### Integration Testing

- Run full `test_folder_quality_schedule.py` (existing)
- Run full `test_image_phase_ops.py` (existing)
- Verify API endpoints work unchanged
- Verify pipeline orchestration unchanged

### Performance Testing

- Benchmark key queries before/after (images, folders, jobs)
- Verify no connection pool regression
- Profile memory usage (should improve via lazy loading)

---

## Success Criteria

| Criterion | Target | Validation |
|-----------|--------|-----------|
| `db.py` size reduction | < 2,500 LOC | `wc -l modules/db.py` |
| Backward compatibility | 100% | All existing imports work |
| Test coverage | ≥ 85% | `pytest --cov` |
| Performance | Zero regression | Benchmark suite passes |
| Defect isolation | 100% | No cross-module breakage |
| New import adoption | 50% of new code | Code review checkpoints |

---

## Risk Mitigation

### Risk 1: Circular Dependencies

**Problem:** Submodules depend on each other (e.g., `images.py` ↔ `keywords.py`).

**Mitigation:**
- Use dependency injection: pass callables, not imported modules
- Create thin adapters in `connection.py`
- Test in isolation with mock functions

**Example:**
```python
# ❌ Circular dependency
# db/images.py imports db.keywords
# db/keywords.py imports db.images

# ✅ Dependency injection
def update_image_metadata(image_id, keywords_fn):
    """keywords_fn: callable to sync keywords separately"""
    # ... image update ...
    keywords_fn(image_id, keywords_csv)
```

---

### Risk 2: Breaking Import Changes

**Problem:** Developers import internals via `db.py`; migration breaks them.

**Mitigation:**
- All functions remain re-exported in `db.py` (backward compatible)
- Use deprecation warnings, not immediate removal
- 6-month deprecation period before removing re-exports
- Document new import paths in CLAUDE.md

---

### Risk 3: Test Suite Fragmentation

**Problem:** Existing tests tightly coupled to `db.py` structure.

**Mitigation:**
- Keep `test_db.py` unchanged (tests the facade)
- Add new module-specific tests incrementally
- Don't remove existing tests; just add new ones

---

### Risk 4: Merge Conflicts During Transition

**Problem:** Long-running branch → high conflict risk.

**Mitigation:**
- Use feature branches for each phase
- Merge frequently (weekly)
- Keep facade in sync with submodules
- Use `tools/db_import_audit.py` to detect import regressions

---

## Rollback Plan

If a phase fails:

1. **Revert to previous commit:** `git revert <phase-commit>`
2. **Restore `db.py`:** `git checkout <parent-commit> modules/db.py`
3. **Keep test additions:** No rollback needed; they pass with old code
4. **Assess blocking issue:** Use learnings to adjust subsequent phases

---

## Long-Term Benefits

### For Development

- **Single-responsibility modules:** 600–1,500 LOC each (manageable)
- **Faster merge cycles:** Changes isolated by domain
- **Easier onboarding:** New developers find related functions in one place
- **Better code review:** PRs touch 2–3 modules max, not 414 KB

### For Testing

- **Isolated unit tests:** Test image logic without job machinery
- **Reduced fixtures:** Mock only what's needed
- **Faster test runs:** Parallel test execution now practical
- **Better coverage:** Each module's responsibility is clear

### For Maintenance

- **AI-friendly:** Small modules fit in LLM context windows
- **Reusability:** Extract modules for CLI tools, batch jobs
- **Deprecation:** Retire old code paths incrementally
- **Migration:** Support Firebird → PostgreSQL cutover in Phase 4

### For Architecture

- **Testable:** Connector abstraction fully realized
- **Flexible:** Swap backends (API, cache, alternative DB)
- **Observable:** Telemetry module standardizes logging
- **Resilient:** Backup module enables disaster recovery

---

## Implementation Checklist

- [ ] **Phase 1 (Weeks 1–2)**
  - [ ] Create `modules/db/` package
  - [ ] Extract `connection.py`
  - [ ] Extract `telemetry.py`
  - [ ] Update `db.py` re-exports
  - [ ] Full test suite pass
  - [ ] Zero import regressions

- [ ] **Phase 2 (Weeks 3–6)**
  - [ ] Extract `images.py`
  - [ ] Extract `folders.py`
  - [ ] Extract `stacks.py`
  - [ ] Extract `keywords.py`
  - [ ] Test isolation for each module
  - [ ] Update `db.py` re-exports

- [ ] **Phase 3 (Weeks 7–8)**
  - [ ] Consolidate `jobs.py`
  - [ ] Add recovery functions
  - [ ] State machine tests
  - [ ] Integration tests pass

- [ ] **Phase 4 (Weeks 9–10)**
  - [ ] Extract `embeddings.py`
  - [ ] Extract `backup.py`
  - [ ] Final `db.py` → facade refactor
  - [ ] Performance benchmarks pass

- [ ] **Phase 5 (Week 11)**
  - [ ] Add deprecation warnings
  - [ ] Write migration guide
  - [ ] Update CLAUDE.md
  - [ ] Final validation

---

## Next Steps

1. **Review & Approval:** Share plan with team; gather feedback
2. **Spike (Phase 1):** Extract `connection.py` & `telemetry.py` as proof-of-concept
3. **Iterate:** Adjust plan based on spike learnings
4. **Execute:** Run 5 phases over 11 weeks with weekly releases

---

## References

- **Current State:** `modules/db.py` (414 KB, 10,565 LOC)
- **Code Review:** `docs/reports/CODE_DESIGN_REVIEW_2026-04-18.md` (M-1)
- **Connector Architecture:** `docs/architecture/DB_CONNECTOR.md`
- **Phase 4 Keywords:** `docs/planning/database/PHASE4_KEYWORDS_DEPRECATION.md`
