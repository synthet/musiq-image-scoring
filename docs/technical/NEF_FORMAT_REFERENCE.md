# Nikon NEF — format notes (reference)

This document summarizes structural and metadata facts about **Nikon Electronic Format (NEF)** that matter when implementing **preview extraction**, **thumbnails**, and **delegated raw decode** in this stack. It is aligned with community documentation (ExifTool, LibRaw/dcraw, RawDigger analyses) and internal deep-research notes; Nikon does not publish a full public raw specification.

**Scope:** Container layout, embedded previews, compression families at a high level. This project does **not** implement Bayer decode in application code; LibRaw/rawpy/dcraw handle sensor data.

---

## Container and byte order

- NEF is based on **TIFF / TIFF-EP**: an 8-byte TIFF header (byte order, magic `42`, offset to IFD0).
- **Byte order:** Most DSLR/mirrorless NEFs are **big-endian** (`MM`). Little-endian (`II`) exists in rare early or compact-camera cases—robust parsers check the first two bytes.
- **IFD0** holds baseline tags, pointers to **EXIF** and often **SubIFDs** (tag **330** decimal = **0x014A** hex: “SubIFDs” / child IFDs).

---

## IFD layout by “class” (simplified)

| Aspect | Typical pattern |
|--------|-------------------|
| Older / class 0–1 | IFD0 only or IFD0 + one SubIFD for raw; preview may be small JPEG in IFD0 or first SubIFD. |
| D3-era / class 2 | IFD0 + SubIFD(s): often one stream for **large embedded JPEG**, another for **CFA raw**. |
| D4 / Z series / class 3 | IFD0 + **multiple SubIFDs**; **MakerNote** may point to an additional **preview IFD**. |

**Practical consequence:** The “best” embedded preview is **not** always the first `FF D8` in the file; it may be the largest JPEG, or the one referenced by TIFF tags / MakerNote.

---

## EXIF and Nikon MakerNote

- **EXIF IFD** (pointer from IFD0) contains standard tags and **MakerNote** (tag **0x927C**).
- **Nikon3** MakerNote is common from roughly the D2X/D70 era through current mirrorless; it contains hundreds of proprietary tags.
- **Preview via MakerNote:** Tag **0x0011** (*PreviewImage*) can point to an internal **preview IFD** where tags **0x0201** / **0x0202** (*JPEGInterchangeFormat* / *Length*) give offset and size of an embedded JPEG. Tools like ExifTool follow this automatically.

---

## Compression and raw payload (decoder responsibility)

Application code in this repo **does not** unpack CFA data. For completeness:

| TIFF `Compression` | Meaning (high level) |
|--------------------|----------------------|
| **1** | Uncompressed |
| **32769** | Packed / padded layouts on some older 12-bit bodies |
| **34713** | Nikon’s “lossless” Huffman-style scheme (often what people mean by “Nikon lossless NEF”) |

**MakerNote** tag **0x0093** (*NEFCompression*) and related tags (e.g. linearization / color balance) matter to **LibRaw/dcraw**, not to JPEG preview extraction.

**Pitfalls called out in literature:** D100-era **wrong compression flags**; **encrypted** MakerNote fields (e.g. color balance) for WB—preview JPEGs are still extractable without decrypting those for display.

---

## Thumbnail vs full / large preview

- Many NEFs contain a **small baseline JPEG** (e.g. thumbnail-sized) **and** a **larger** embedded preview.
- Heuristics that take the **first** sufficiently large SOI/EOI region can pick the **thumbnail** instead of the main preview.
- Prefer: **tag-driven** extraction (ExifTool `-JpgFromRaw` / `-PreviewImage`, or TIFF/MakerNote offsets) or **largest valid JPEG** heuristic when scanning.

---

## Target camera families (product support)

| Body | Notes relevant to previews |
|------|----------------------------|
| **Nikon D90** | Older 12-bit pipeline; embedded sizes vary—**width-only** gates can reject valid previews. |
| **Nikon D300** | 14-bit, class-2-style layouts; large SubIFD JPEG common. |
| **Nikon Z 6II** | Class-3–style TIFF; multiple SubIFDs; MakerNote preview common—**ExifTool-first** is reliable. |
| **Nikon Z 8** | Same broad family; some capture modes stress decoders—**embedded JPEG via ExifTool** should remain primary for UI; full decode may fall back to LibRaw/ImageMagick. |

---

## Recommended extraction strategy (conceptual)

1. **Prefer ExifTool** (or equivalent) for **`-JpgFromRaw`** then **`-PreviewImage`** when building thumbnails/previews.
2. **Fallback:** embedded JPEG via **dcraw -e** (embedded extract) where appropriate.
3. **Full raster for scoring/UI:** **rawpy** (LibRaw) or **ImageMagick** when embedded preview is missing or insufficient—accept that **very new** bodies may require updated LibRaw.
4. **Avoid** relying on naive **first-FF-D8** scans as the only path for production UI.

---

## Related project docs

- [`RAW_PROCESSING_GUIDE.md`](./RAW_PROCESSING_GUIDE.md) — conversion chain for ML and tooling.
- [`NEF_IMPLEMENTATION_REVIEW.md`](./NEF_IMPLEMENTATION_REVIEW.md) — how this repository and the Electron gallery implement the above.
