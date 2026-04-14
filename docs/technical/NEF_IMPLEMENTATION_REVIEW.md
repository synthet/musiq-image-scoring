# NEF handling — implementation review

**Date:** 2026-04-13  
**Scope:** How **image-scoring-backend** and **image-scoring-gallery** read **Nikon NEF** files for previews, thumbnails, and ML-facing rasterization—reviewed against the structural notes in [`NEF_FORMAT_REFERENCE.md`](./NEF_FORMAT_REFERENCE.md).

**Support goal:** Reliable behavior for **D90**, **D300**, **Z 6II**, and **Z 8** (embedded preview and delegated raw decode).

---

## Executive summary

- **Strong:** Both projects rely on **ExifTool** (and fallbacks) for embedded JPEG extraction where it matters for production quality. That matches the reference document: previews are best obtained via **tag-driven** extraction, not blind byte scans.
- **Weaker:** Legacy **browser-side** JPEG discovery in the backend Gradio asset bundle uses a **first-match** heuristic that does not match NEF’s multi-JPEG layout. A **minimum width** rule in **preview generation** may unnecessarily force **full raw decode** for some older bodies with legitimately smaller embedded previews.

---

## image-scoring-backend

### `modules/thumbnails.py`

| Function / path | Role | Assessment |
|-----------------|------|------------|
| `extract_embedded_jpeg()` | `-JpgFromRaw`, then `-PreviewImage`, then `dcraw -e` | **Aligned** with reference: ExifTool resolves SubIFDs and MakerNote preview IFDs without custom TIFF walks. |
| `generate_thumbnail()` | Embedded JPEG → **rawpy** → **ImageMagick** | Reasonable; full decode is delegated to LibRaw. |
| `generate_preview()` | Uses `extract_embedded_jpeg()`, then rejects if `img.width <= 1000` before saving | **Risk:** Some **D90** / older shots can have a valid “main” embedded preview **≤1000 px** wide. That forces **rawpy** or failure though ExifTool already returned a usable image. Consider pixel-area rules, larger min width only for “thumbnail-like” sizes, or trusting ExifTool’s choice. |
| `open_image_for_ml()` | Same chain as thumbnails | Appropriate for tagging/scoring pipelines. |

### Gradio / static UI: `modules/ui/assets.py` (`NefViewer` in embedded JS)

- **Client `extractEmbeddedJpeg`:** Scans for **first** `FF D8` after 1KB with “enough file left,” then finds an EOI.
- **Issue:** Per reference, NEFs often contain a **small thumbnail JPEG** and a **larger** preview; first-match can select the wrong image. The **Electron gallery** implementation instead prefers the **largest** complete JPEG above a size floor—closer to best practice.
- **Mitigation in practice:** The UI prefers **`/api/raw-preview`**, which uses **`thumbnails.generate_preview()`** (ExifTool-first). Client-side extraction is a fallback when the server path fails.

### API

- **`GET /raw-preview`** → `thumbnails.generate_preview()` — **authoritative** for server-side preview quality.

---

## image-scoring-gallery

### `electron/nefExtractor.ts`

- Uses **exiftool-vendored** `extractJpgFromRaw` and reapplies **Orientation** to the extracted JPEG.
- **Assessment:** **Best tier** for **Z 6II**, **Z 8**, **D300**, and typical **D90** files; matches reference (MakerNote + SubIFD handling delegated to ExifTool).

### `electron/main.ts` — IPC `nef:extract-preview`

- Runs `NefExtractor` only for extension **`.nef`**; other raw extensions return the **raw file buffer** for renderer-side fallbacks.
- **Note:** **`.nrw`** (Coolpix-style) differs from DSLR NEF layout in the reference doc; client SubIFD heuristics may not apply—acceptable if product scope is DSLR NEF-only.

### `src/utils/nefViewer.ts`

| Tier | Behavior | Assessment |
|------|----------|------------|
| 1 | IPC → ExifTool extraction | Primary; robust. |
| 2 | TIFF IFD0 tag **0x014A** (SubIFDs), then **0x0201** / **0x0202** in each SubIFD | Matches common **class-2/3** layouts; **does not** walk **EXIF → MakerNote → 0x0011** preview IFD—Tier 1 covers that. |
| 3 | Scan all SOI markers; pick **largest** JPEG &gt; 10KB | Good fallback vs “first JPEG” heuristics; aligns with reference (avoid thumbnail-only). |

**Non-Electron builds:** Without IPC, `extractWithFallback` cannot run Tier 1; Tier 2/3 only run when the app provides a file buffer (e.g. after failed extraction paths).

---

## Camera-specific checklist (requirements vs code)

| Camera | Expectation | Code posture |
|--------|-------------|--------------|
| **D90** | Variable embedded preview sizes; small thumb + larger JPEG possible | ExifTool-first **OK**. Watch **`generate_preview` width &gt;1000** gate. Prefer largest-JPEG or tag-driven fallbacks over first-SOI in JS. |
| **D300** | 14-bit, large SubIFD preview common | ExifTool + SubIFD Tier 2 generally sufficient. |
| **Z 6II** | Multiple SubIFDs + MakerNote | Tier 1 essential for edge cases; Tier 2 partial. |
| **Z 8** | Newer modes may stress **rawpy** | Comments in backend already note possible rawpy failure; **ExifTool embedded path** should remain primary for UI. |

---

## Recommendations (prioritized)

1. **Backend Gradio JS (`assets.py`):** Align embedded-JPEG fallback with gallery behavior—e.g. **largest valid JPEG** above a size threshold—or **remove** redundant client extraction when `/api/raw-preview` is available.
2. **`generate_preview()`:** Revisit **`img.width > 1000`**; use combined criteria (dimensions, byte size, or “accept ExifTool’s first successful extract unless clearly thumbnail-sized”).
3. **Documentation:** Keep [`NEF_FORMAT_REFERENCE.md`](./NEF_FORMAT_REFERENCE.md) as the single structural reference; update this file when changing extraction chains or IPC behavior.
4. **Tests:** Regression tests using real samples under `tests/fixtures/testing_samples/` (D90, D300, Z6II, Z8) for `extract_embedded_jpeg` / preview generation are valuable when touching thumbnail logic.

---

## File index

| Location | Responsibility |
|----------|----------------|
| `image-scoring-backend/modules/thumbnails.py` | Embedded JPEG, thumbnails, previews, ML open |
| `image-scoring-backend/modules/api.py` | `GET /raw-preview` |
| `image-scoring-backend/modules/ui/assets.py` | Gradio `NefViewer` JS (fallback extraction) |
| `image-scoring-gallery/electron/nefExtractor.ts` | ExifTool extraction in Electron |
| `image-scoring-gallery/electron/main.ts` | IPC `nef:extract-preview` |
| `image-scoring-gallery/src/utils/nefViewer.ts` | Tiered client fallbacks |
