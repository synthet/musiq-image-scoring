# AI Culling Feature - Technical Documentation

**Version**: 3.6.0  
**Date**: 2025-12-26  
**Status**: Implementation Complete

---

## Overview

The Culling feature provides an Aftershoot-style AI workflow for photographers to quickly sort through photo shoots. It groups similar images (bursts, duplicates), auto-picks the best shot in each group based on quality scores, and exports decisions to XMP sidecar files for Lightroom Cloud integration.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        WebUI (webui.py)                      │
│  ┌─────────────────────────────────────────────────────────┐│
│  │                    Culling Tab                          ││
│  │  • Folder input / controls                              ││
│  │  • Run button / results display                         ││
│  │  • Picks gallery                                        ││
│  └─────────────────────────────────────────────────────────┘│
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                  modules/culling.py                          │
│  ┌─────────────────────────────────────────────────────────┐│
│  │                 CullingEngine                           ││
│  │  • create_session()   → Creates DB session              ││
│  │  • import_images()    → Groups via clustering.py        ││
│  │  • auto_pick_all()    → Selects best per group          ││
│  │  • export_to_xmp()    → Writes XMP sidecars             ││
│  │  • run_full_cull()    → One-shot workflow               ││
│  └─────────────────────────────────────────────────────────┘│
└────────────┬────────────────────────────────┬───────────────┘
             │                                │
┌────────────▼────────────┐    ┌──────────────▼───────────────┐
│   modules/clustering.py │    │       modules/xmp.py         │
│  (Existing)             │    │  (New)                       │
│  • MobileNetV2 features │    │  • read_xmp()                │
│  • Agglomerative        │    │  • write_rating()            │
│    Clustering           │    │  • write_label()             │
│                         │    │  • write_culling_results()   │
└─────────────────────────┘    └──────────────────────────────┘
             │                                │
┌────────────▼────────────────────────────────▼───────────────┐
│                      modules/db.py                           │
│  Tables: culling_sessions, culling_picks                     │
│  Functions: create_culling_session, get_session_groups, etc. │
└─────────────────────────────────────────────────────────────┘
```

---

## Database Schema

### culling_sessions

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Session ID |
| folder_path | TEXT | Source folder |
| mode | TEXT | 'automated' or 'assisted' |
| status | TEXT | 'active', 'completed', 'exported' |
| total_images | INTEGER | Count of images in session |
| total_groups | INTEGER | Count of similarity groups |
| reviewed_groups | INTEGER | Groups with decisions |
| picked_count | INTEGER | Images marked as picks |
| rejected_count | INTEGER | Images marked as rejects |
| created_at | TIMESTAMP | Session creation time |
| completed_at | TIMESTAMP | Session completion time |

### culling_picks

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Pick ID |
| session_id | INTEGER FK | Reference to session |
| image_id | INTEGER FK | Reference to images table |
| group_id | INTEGER | Similarity group ID |
| decision | TEXT | 'pick', 'reject', 'maybe', NULL |
| auto_suggested | BOOLEAN | True if AI suggested |
| is_best_in_group | BOOLEAN | True if best of its group |
| created_at | TIMESTAMP | Decision time |

**Indexes**:
- `idx_culling_picks_session` on (session_id)
- `idx_culling_picks_image` on (image_id)

---

## XMP Sidecar Format

XMP sidecars are written following Adobe's XMP specification for Lightroom compatibility:

```xml
<?xml version="1.0" encoding="utf-8"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:Description rdf:about=""
      xmlns:xmp="http://ns.adobe.com/xap/1.0/"
      xmp:Rating="4"
      xmp:Label="Green"
      xmp:Picked="true"
      xmp:ModifyDate="2025-12-26T23:30:00"/>
  </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>
```

**Field Mapping**:
| Decision | Rating | Label | Picked |
|----------|--------|-------|--------|
| Pick | 4 | Green | true |
| Reject | 1 | Red | false |

> **Note**: The `xmp:Picked` attribute is a **custom field** for internal tracking only. Lightroom Classic/Cloud does not recognize this attribute natively. The actual pick/reject signaling that Lightroom reads is conveyed through the `xmp:Rating` and `xmp:Label` fields (e.g., Green = pick, Red = reject).

---

## API Reference

### CullingEngine

```python
class CullingEngine:
    def create_session(folder_path: str, mode: str = 'automated') -> int
    def import_images(session_id: int, distance_threshold: float, time_gap_seconds: int) -> dict
    def auto_pick_all(session_id: int, score_field: str = 'score_general') -> dict
    def export_to_xmp(session_id: int, pick_rating: int = 4, reject_rating: int = 1) -> dict
    def run_full_cull(folder_path: str, **kwargs) -> dict
```

### XMP Functions

```python
def read_xmp(image_path: str) -> dict
def write_rating(image_path: str, rating: int) -> bool
def write_label(image_path: str, label: str) -> bool
def write_pick_flag(image_path: str, is_picked: bool) -> bool
def write_culling_results(image_path: str, rating: int, label: str, is_picked: bool) -> bool
```

### DB Functions (New)

```python
def create_culling_session(folder_path, mode) -> int
def get_culling_session(session_id) -> dict
def get_active_culling_sessions() -> list
def update_culling_session(session_id, **kwargs) -> bool
def add_images_to_culling_session(session_id, image_ids, group_assignments) -> bool
def set_pick_decision(session_id, image_id, decision, auto_suggested) -> bool
def set_best_in_group(session_id, image_id, group_id) -> bool
def get_session_picks(session_id, decision_filter) -> list
def get_session_groups(session_id) -> list
def get_session_stats(session_id) -> dict
```

---

## Workflow

### AI-Automated Culling

1. **Create Session** - Initialize DB record with folder path
2. **Import Images** - Query DB for scored images in folder
3. **Cluster** - Use existing `clustering.py` to find similar groups
4. **Map Groups** - Associate image_ids with stack_ids as group_ids
5. **Auto-Pick** - For each group, pick highest `score_general`
6. **Reject Rest** - Mark non-picked images in groups as rejects
7. **Export XMP** - Write `.xmp` sidecar files next to originals

---

## Files Changed

| File | Lines Added | Description |
|------|------------|-------------|
| `modules/xmp.py` | ~285 | New XMP sidecar handler |
| `modules/culling.py` | ~320 | New CullingEngine class |
| `modules/db.py` | ~300 | Tables + helper functions |
| `webui.py` | ~125 | Culling tab UI + handlers |

---

## Design Decisions

1. **Reuse Stacks Infrastructure** - Culling groups leverage existing `clustering.py` and stack_id assignments to avoid code duplication.

2. **Non-Destructive XMP** - All metadata is written to sidecar files, never touching original RAW/JPEG files.

3. **Session-Based Workflow** - Culling sessions are persisted to DB, allowing resume/review of previous culls.

4. **Lightroom Cloud Compatible** - XMP schema follows Adobe's standard for ratings and labels.

5. **AI-Automated First** - Implemented auto-pick mode as requested; assisted mode can be added later.

---

## Testing

- [x] Python syntax check passed
- [ ] Integration test with sample scored folder
- [ ] Verify XMP creation for picks/rejects
- [ ] Import into Lightroom Cloud and verify ratings

---

## Future Enhancements

- **AI-Assisted Mode** - User picks with AI suggestions
- **Face Detection** - Prioritize expressions for portraits
- **Capture One Support** - Additional XMP fields for C1
- **Session Resume** - UI to continue previous sessions

## Related Documents

- [Docs index](../README.md)
- [TODO / roadmap](../../TODO.md)
- [Stacks manual management](STACKS_MANUAL_MANAGEMENT.md)
- [XMP](../../modules/xmp.py)
- [Culling done but no stacks (investigation, 2026-03)](../reports/CULLING_NO_STACKS_INVESTIGATION_2026-03-15.md)

