# CLIP accessibility metadata

IPTC **Alt Text Accessibility** and **Extended Description Accessibility** are generated from CLIP cosine similarity against a prompt bank (`data/clip_accessibility_prompts.txt`), not from BLIP captions.

## Storage

| Layer | Field / tag |
|-------|-------------|
| XMP sidecar | `iptcCore:AltTextAccessibility`, `iptcCore:ExtDescrAccessibility` (`rdf:Alt` / `x-default`) |
| Embedded file | `XMP-iptcCore:AltTextAccessibility`, `XMP-iptcCore:ExtDescrAccessibility` (via exiftool) |
| PostgreSQL | `image_xmp.alt_text`, `image_xmp.extended_description` |

## Configuration (`config.json` → `tagging`)

| Key | Default | Meaning |
|-----|---------|---------|
| `accessibility_default` | `false` | Enable during batch tagging and pipeline keywords phase |
| `accessibility_prompts_file` | `data/clip_accessibility_prompts.txt` | Prompt bank path (relative to repo root) |
| `accessibility_top_k_alt` | `2` | Prompts merged into alt text |
| `accessibility_top_k_extended` | `5` | Prompts in extended description |
| `alt_text_max_chars` | `200` | Alt text length cap |
| `extended_max_chars` | `1000` | Extended description cap |

## API

- `POST /api/tagging/start` — `generate_accessibility` (boolean)
- `POST /api/tagging/single` — `generate_accessibility` (boolean)
- `POST /api/pipeline/submit` / runs submit — `generate_accessibility` when keywords stage runs

## Maintenance

```bash
# WSL + ~/.venvs/tf
python scripts/maintenance/backfill_accessibility_xmp.py --folder /mnt/d/Photos/2024 --limit 100
```

Uses stored CLIP 512-d embeddings when present; otherwise runs CLIP on the image (or NEF thumbnail).

## Module

Implementation: `modules/clip_accessibility.py`. Wired from `modules/tagging.py` after keyword tagging when `generate_accessibility` is true.
