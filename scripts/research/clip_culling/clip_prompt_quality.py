#!/usr/bin/env python3
"""Offline CLIP prompt-quality benchmark over the seeded E2E corpus.

Estimates generic photo-quality / reject-reason signals from **persisted** CLIP
image embeddings + zero-shot text prompts (CLIP-IQA antonym style). Treated as an
*auxiliary* signal, not a primary IQA model. No DB/API/schema changes — read-only
against the E2E DB (``image_scoring_test`` @5433, pinned by ``common``), CSV out.

Dimensions (prompt_set_version ``v0``):

    clip_quality_v0  clip_focus_v0  clip_exposure_v0  clip_noise_v0
    clip_misshot_v0  clip_composition_v0  clip_wildlife_quality_v0

Each dimension compares the image to a positive and a negative prompt bank. We
report two readings per dimension:

* ``*_margin``  = mean cos(img, pos) - mean cos(img, neg)   (raw, can be tiny)
* ``*_score``   = antonym softmax prob of pos vs neg at the model's logit scale
  (a real 0..1 spread; the spec's literal ``sigmoid(pos-neg)`` collapses to ~0.5
  because cosine margins are ~0.01-0.05 — softmax/temperature is the CLIP-IQA fix).

Spaces are compared **only** if their persisted image embeddings have a matching
*text* tower (image/text encoder mismatch silently corrupts cosine):

    clip_vit_b32_image          HF openai/clip-vit-base-patch32   (512-d)
    openai_clip_vit_l14_image   open_clip ViT-L-14-quickgelu/openai
    openclip_l14_laion2b_image  open_clip ViT-L-14/laion2b_s32b_b82k
    siglip2_base_image          HF google/siglip2-base-patch16-224
    bioclip_2_image             open_clip hf-hub:imageomics/bioclip-2

DINOv2 / MobileNet are image-only and skipped.

Template expansion: short adjectival phrases are expanded through 6 caption
templates and averaged; full descriptive captions (containing photo/image/bird/
wildlife) are used verbatim to avoid ungrammatical prompts.

Runs **read-only** against the app's configured Postgres (``database.engine`` /
``db_postgres.get_pg_config``) — production by default. Only SELECTs are issued;
no DB/API/schema changes. Spaces with no persisted embeddings are skipped.

Run in WSL with the app venv::

    source ~/.venvs/tf/bin/activate
    python -m scripts.research.clip_culling.clip_prompt_quality --spaces all
    python -m scripts.research.clip_culling.clip_prompt_quality --folders 62,44,45 --limit 2000

Ground truth for evaluation is **human** ``rating`` (1-5) + ``label`` (color);
``cull_decision`` is MobileNet-pipeline-derived and only carried for reference.
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.research.clip_culling.wrappers import (  # noqa: E402
    HFImageTower, Tower, l2_normalize,
)

logger = logging.getLogger("clip_culling.prompt_quality")

PROMPT_SET_VERSION = "v0"
RESULTS_DIR = PROJECT_ROOT / "reports" / "clip-culling" / "prompt-quality"

# --------------------------------------------------------------------------- #
# Prompt template expansion
# --------------------------------------------------------------------------- #
TEMPLATES = (
    "a photo that is {phrase}",
    "a photograph that is {phrase}",
    "an image that is {phrase}",
    "a {phrase} photograph",
    "a {phrase} image",
    "this is a {phrase} photo",
)

# Phrases containing these tokens are full captions -> used verbatim (no template).
_VERBATIM_TOKENS = ("photo", "photograph", "image", "bird", "wildlife", "subject")


def _is_verbatim(phrase: str) -> bool:
    p = phrase.lower()
    return any(tok in p for tok in _VERBATIM_TOKENS)


def expand(phrase: str) -> list[str]:
    """Return the prompt variants for *phrase* (templated, or verbatim)."""
    if _is_verbatim(phrase):
        return [phrase]
    return [t.format(phrase=phrase) for t in TEMPLATES]


# --------------------------------------------------------------------------- #
# Prompt banks (from the experiment spec)
# --------------------------------------------------------------------------- #
GOOD = [
    "high quality", "good", "beautiful", "sharp", "clear", "well focused",
    "properly exposed", "clean", "detailed", "professional", "well composed",
    "visually pleasing", "good lighting", "natural colors",
    "a photo with strong subject separation", "crisp details",
    "a photo with a clear subject", "balanced contrast", "good dynamic range",
    "a keeper photo",
]
BAD = [
    "low quality", "bad", "poor", "blurry", "out of focus", "misfocused",
    "overexposed", "underexposed", "noisy", "grainy", "soft", "dull",
    "washed out", "poorly composed", "a photo with no clear subject",
    "a missed shot", "a poorly timed photo", "technically flawed",
    "bad lighting", "a rejected photo",
]

FOCUS_POS = [
    "sharp", "tack sharp", "well focused", "crisp and detailed",
    "a photo with clear fine details", "a photo with a sharp subject",
    "a photo with sharp eyes", "a photo with detailed texture",
]
FOCUS_NEG = [
    "blurry", "out of focus", "misfocused", "soft", "motion blurred",
    "a photo with camera shake", "a photo with smeared details",
    "a photo with an unsharp subject", "a photo with blurry eyes",
]

EXPO_POS = [
    "properly exposed", "well exposed", "a photo with balanced highlights and shadows",
    "a photo with good dynamic range", "a photo with preserved highlight detail",
    "a photo with visible shadow detail", "naturally lit",
]
EXPO_NEG = [
    "overexposed", "underexposed", "blown out", "a photo with clipped highlights",
    "a photo with crushed shadows", "too dark", "too bright", "washed out",
    "harshly lit",
]

NOISE_POS = [
    "clean", "smooth", "a photo with low noise", "a photo with clean details",
    "a photo with a smooth background", "a high quality clean image",
]
NOISE_NEG = [
    "noisy", "grainy", "a high ISO noisy photo", "a photo with color noise",
    "a photo with luminance noise", "a photo with rough background noise",
    "a photo with digital artifacts", "degraded",
]

MISSHOT_POS = [
    "well timed", "a photo with a clear subject", "a photo with good subject placement",
    "well composed", "a photo with an interesting pose", "a photo with good eye contact",
    "a photo capturing the decisive moment",
]
MISSHOT_NEG = [
    "a missed shot", "a poorly timed photo", "a photo with no clear subject",
    "a photo with the subject cut off", "a photo with a hidden subject",
    "a photo with the subject facing away", "a photo with awkward framing",
    "a poorly composed photo", "a throwaway photo",
]

COMP_POS = [
    "a photo with beautiful composition", "a photo with balanced composition",
    "visually pleasing", "a photo with strong subject separation",
    "a photo with good background blur", "a photo with harmonious colors",
    "a photo with pleasing light", "professional looking",
]
COMP_NEG = [
    "poorly composed", "cluttered", "a photo with a distracting background",
    "boring", "flat", "messy", "a photo with bad framing",
    "a photo with awkward cropping", "a photo with distracting elements",
]

WILDLIFE_POS = [
    "a bird photo with a sharp eye", "a bird photo with crisp feather detail",
    "a bird photo with a well focused subject", "a wildlife photo with sharp eyes",
    "a bird in its natural habitat", "a striking wildlife photo",
]
WILDLIFE_NEG = [
    "a bird photo with an out of focus eye", "a bird photo with blurry feathers",
    "a bird photo with a soft subject", "a wildlife photo with blurry eyes",
    "a photo with a bird facing away", "a photo with a bird cut off",
    "a photo with a bird hidden behind branches", "a photo with obstructing branches",
]

# dimension name -> (positive phrases, negative phrases)
DIMENSIONS: dict[str, tuple[list[str], list[str]]] = {
    "clip_quality_v0": (GOOD, BAD),
    "clip_focus_v0": (FOCUS_POS, FOCUS_NEG),
    "clip_exposure_v0": (EXPO_POS, EXPO_NEG),
    "clip_noise_v0": (NOISE_POS, NOISE_NEG),
    "clip_misshot_v0": (MISSHOT_POS, MISSHOT_NEG),
    "clip_composition_v0": (COMP_POS, COMP_NEG),
    "clip_wildlife_quality_v0": (WILDLIFE_POS, WILDLIFE_NEG),
}

# --------------------------------------------------------------------------- #
# Space -> text tower registry (must match the image encoder that produced the
# persisted embeddings). DINOv2/MobileNet omitted: no text encoder.
# --------------------------------------------------------------------------- #
OPEN_CLIP_SPACES: dict[str, tuple[str, str | None]] = {
    "openai_clip_vit_l14_image": ("ViT-L-14-quickgelu", "openai"),
    "openclip_l14_laion2b_image": ("ViT-L-14", "laion2b_s32b_b82k"),
    "bioclip_2_image": ("hf-hub:imageomics/bioclip-2", None),
}
SIGLIP2_SPACES = {"siglip2_base_image": "google/siglip2-base-patch16-224"}
HF_CLIP_SPACES = {"clip_vit_b32_image"}  # HF openai/clip-vit-base-patch32

ALL_TEXT_SPACES = (
    list(HF_CLIP_SPACES) + list(OPEN_CLIP_SPACES) + list(SIGLIP2_SPACES)
)


# --------------------------------------------------------------------------- #
# Text encoders (one per tower family)
# --------------------------------------------------------------------------- #
class _B32TextTower:
    """HF ``openai/clip-vit-base-patch32`` text tower (batched), 512-d."""

    def __init__(self):
        self._cache: dict = {}

    def encode_text(self, prompts: list[str]) -> np.ndarray:
        import torch
        from transformers import CLIPModel, CLIPProcessor

        from modules import config

        if "model" not in self._cache:
            name = config.get_config_section("tagging").get(
                "clip_model", "openai/clip-vit-base-patch32"
            )
            device = "cuda" if torch.cuda.is_available() else "cpu"
            self._cache["model"] = CLIPModel.from_pretrained(name).to(device).eval()
            self._cache["proc"] = CLIPProcessor.from_pretrained(name)
            self._cache["device"] = device
            logger.info("Loaded HF CLIP text tower %s on %s", name, device)
        model, proc, device = (
            self._cache["model"], self._cache["proc"], self._cache["device"]
        )
        out = []
        for i in range(0, len(prompts), 256):
            chunk = prompts[i:i + 256]
            inputs = proc(text=chunk, return_tensors="pt", padding=True, truncation=True)
            inputs = {k: v.to(device) for k, v in inputs.items()}
            with torch.no_grad():
                feats = model.get_text_features(**inputs)
            out.append(feats.detach().cpu().numpy().astype(np.float32))
        return l2_normalize(np.concatenate(out, axis=0))

    def unload(self):
        self._cache.clear()
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001
            pass


def make_text_tower(space_code: str):
    """Return an object exposing ``encode_text(list[str]) -> (n,d) np.ndarray``."""
    if space_code in HF_CLIP_SPACES:
        return _B32TextTower()
    if space_code in OPEN_CLIP_SPACES:
        name, pretrained = OPEN_CLIP_SPACES[space_code]
        return Tower(name, pretrained or "")
    if space_code in SIGLIP2_SPACES:
        return HFImageTower(SIGLIP2_SPACES[space_code], kind="siglip2")
    raise ValueError(f"No text tower mapping for space {space_code!r}")


def _encode_phrase_banks(tower, phrases: list[str]) -> np.ndarray:
    """Encode each phrase (template-averaged) -> (n_phrases, d) L2-normalized."""
    vecs = []
    for phrase in phrases:
        variants = expand(phrase)
        v = tower.encode_text(variants)  # (n_variants, d), normalized
        vecs.append(l2_normalize(v.mean(axis=0)))
    return np.vstack(vecs).astype(np.float32)


# --------------------------------------------------------------------------- #
# Read-only DB loaders (configured engine — production by default)
# --------------------------------------------------------------------------- #
def _folder_clause(folders: list[int] | None) -> str:
    if not folders:
        return ""
    return " AND i.folder_id IN (" + ",".join(str(int(f)) for f in folders) + ")"


def load_meta(folders: list[int] | None, limit: int | None) -> dict[int, dict]:
    """image_id -> metadata (human rating/label + scores/stack/path)."""
    from modules import db_postgres

    sql = (
        "SELECT i.id, i.folder_id, i.stack_id, i.file_path, i.score_general, "
        "i.rating, i.label, i.cull_decision FROM images i "
        "WHERE i.rating IS NOT NULL" + _folder_clause(folders) + " ORDER BY i.id"
    )
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = db_postgres.execute_select(sql)
    return {r["id"]: dict(r) for r in rows}


def _parse_vec(v) -> np.ndarray | None:
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip().lstrip("[").rstrip("]")
        return np.array([float(x) for x in s.split(",")], dtype=np.float32) if s else None
    if isinstance(v, (bytes, bytearray, memoryview)):
        return np.frombuffer(bytes(v), dtype=np.float32).copy()
    return np.asarray(v, dtype=np.float32)


def load_embeddings(space_code: str, folders: list[int] | None,
                    ids: set[int] | None) -> dict[int, np.ndarray]:
    """image_id -> raw vector for ``space_code`` (configured DB, read-only)."""
    from modules import db_postgres
    from modules.db_legacy import _pg_embedding_table_for_dim
    from modules.embedding_spaces import SPACE_DIMS, get_embedding_space_id

    sid = get_embedding_space_id(space_code)
    if sid is None:
        return {}
    dim = SPACE_DIMS.get(space_code)
    table = _pg_embedding_table_for_dim(dim)
    sql = (
        f"SELECT e.image_id, e.embedding FROM {table} e "
        f"JOIN images i ON i.id = e.image_id "
        f"WHERE e.embedding_space_id = %s" + _folder_clause(folders)
    )
    rows = db_postgres.execute_select(sql, (sid,))
    out: dict[int, np.ndarray] = {}
    for r in rows:
        if ids is not None and r["image_id"] not in ids:
            continue
        vec = _parse_vec(r["embedding"])
        if vec is not None:
            out[r["image_id"]] = vec
    return out


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
@dataclass
class DimScore:
    margin: np.ndarray          # (N,) mean(pos) - mean(neg)
    score: np.ndarray           # (N,) antonym softmax prob in [0,1]
    top_pos_idx: np.ndarray     # (N,) argmax positive phrase
    top_neg_idx: np.ndarray     # (N,) argmax negative phrase
    pos_mean: np.ndarray        # (N,) mean positive cosine
    neg_mean: np.ndarray        # (N,) mean negative cosine


def score_dimension(img: np.ndarray, pos_t: np.ndarray, neg_t: np.ndarray,
                    temp: float) -> DimScore:
    pos_cos = img @ pos_t.T  # (N, P)
    neg_cos = img @ neg_t.T  # (N, M)
    pos_mean = pos_cos.mean(axis=1)
    neg_mean = neg_cos.mean(axis=1)
    margin = pos_mean - neg_mean
    logits = np.stack([pos_mean, neg_mean], axis=1) * temp
    logits -= logits.max(axis=1, keepdims=True)
    e = np.exp(logits)
    prob = e[:, 0] / e.sum(axis=1)
    return DimScore(
        margin=margin, score=prob,
        top_pos_idx=pos_cos.argmax(axis=1), top_neg_idx=neg_cos.argmax(axis=1),
        pos_mean=pos_mean, neg_mean=neg_mean,
    )


# --------------------------------------------------------------------------- #
# Ground truth helpers (human labels only)
# --------------------------------------------------------------------------- #
def pick_label(meta: dict) -> str:
    rating = meta.get("rating")
    label = (meta.get("label") or "").lower()
    if (rating is not None and rating <= 2) or label == "red":
        return "rejected"
    if rating is not None and rating >= 4:
        return "picked"
    return "neutral"


def _auc(scores: np.ndarray, positive: np.ndarray) -> float | None:
    """ROC-AUC of `scores` separating positive(=1) from negative(=0). Mann-Whitney."""
    pos = scores[positive == 1]
    neg = scores[positive == 0]
    if pos.size == 0 or neg.size == 0:
        return None
    # rank-based AUC
    allv = np.concatenate([pos, neg])
    order = allv.argsort()
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, allv.size + 1)
    # average ties
    _, inv, counts = np.unique(allv, return_inverse=True, return_counts=True)
    sums = np.zeros(counts.size)
    np.add.at(sums, inv, ranks)
    avg = sums / counts
    ranks = avg[inv]
    r_pos = ranks[: pos.size].sum()
    return float((r_pos - pos.size * (pos.size + 1) / 2) / (pos.size * neg.size))


def _spearman(a: np.ndarray, b: np.ndarray) -> float | None:
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 5:
        return None
    try:
        from scipy.stats import spearmanr
        return round(float(spearmanr(a[m], b[m]).correlation), 4)
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# Per-space run
# --------------------------------------------------------------------------- #
def run_space(space_code: str, meta: dict, temp: float, out_dir,
              folders: list[int] | None) -> dict | None:
    emb_raw = load_embeddings(space_code, folders, set(meta))
    if not emb_raw:
        logger.warning("No persisted embeddings for %s — skipping.", space_code)
        return None
    ids = [i for i in emb_raw if i in meta]
    if not ids:
        logger.warning("No labeled images intersect %s — skipping.", space_code)
        return None
    img = l2_normalize(np.vstack([emb_raw[i] for i in ids]).astype(np.float32))
    logger.info("[%s] %d images (dim=%d)", space_code, len(ids), img.shape[1])

    tower = make_text_tower(space_code)
    dim_scores: dict[str, DimScore] = {}
    bank_text: dict[str, tuple[list[str], list[str], np.ndarray, np.ndarray]] = {}
    try:
        for dim, (pos, neg) in DIMENSIONS.items():
            pos_t = _encode_phrase_banks(tower, pos)
            neg_t = _encode_phrase_banks(tower, neg)
            if pos_t.shape[1] != img.shape[1]:
                logger.error("[%s] text dim %d != image dim %d (tower mismatch!) — skip",
                             space_code, pos_t.shape[1], img.shape[1])
                return None
            dim_scores[dim] = score_dimension(img, pos_t, neg_t, temp)
            bank_text[dim] = (pos, neg, pos_t, neg_t)
    finally:
        if hasattr(tower, "unload"):
            tower.unload()

    # ---- CSV ----
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"clip_prompt_quality__{space_code}.csv"
    dim_names = list(DIMENSIONS)
    header = (
        ["image_id", "file_path", "stack_id", "rating", "label", "cull_decision",
         "picked_or_rejected"]
        + [d for d in dim_names]                       # *_score (0..1)
        + [f"{d}__margin" for d in dim_names]
        + ["top_positive_prompt", "top_negative_prompt"]
        + [f"{d}__pos_sim" for d in dim_names]
        + [f"{d}__neg_sim" for d in dim_names]
        + ["prompt_set_version", "space"]
    )
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        q = dim_scores["clip_quality_v0"]
        gpos, gneg, _, _ = bank_text["clip_quality_v0"]
        for k, iid in enumerate(ids):
            m = meta[iid]
            row = [
                iid, m.get("file_path"), m.get("stack_id"), m.get("rating"),
                m.get("label"), m.get("cull_decision"), pick_label(m),
            ]
            row += [round(float(dim_scores[d].score[k]), 4) for d in dim_names]
            row += [round(float(dim_scores[d].margin[k]), 4) for d in dim_names]
            row += [gpos[int(q.top_pos_idx[k])], gneg[int(q.top_neg_idx[k])]]
            row += [round(float(dim_scores[d].pos_mean[k]), 4) for d in dim_names]
            row += [round(float(dim_scores[d].neg_mean[k]), 4) for d in dim_names]
            row += [PROMPT_SET_VERSION, space_code]
            w.writerow(row)
    logger.info("[%s] wrote %s", space_code, csv_path)

    # ---- evaluation ----
    rating = np.array([float(meta[i].get("rating") or np.nan) for i in ids])
    picks = np.array([pick_label(meta[i]) for i in ids])
    keeper = (picks == "picked").astype(int)
    reject = (picks == "rejected").astype(int)
    pr_mask = (keeper == 1) | (reject == 1)

    # within-stack separation (keeper vs reject inside the same stack)
    stack_of = np.array([meta[i].get("stack_id") for i in ids])
    metrics = {"space": space_code, "n_images": len(ids), "dim_dim": int(img.shape[1]),
               "n_picked": int(keeper.sum()), "n_rejected": int(reject.sum()),
               "dimensions": {}}
    for dim in dim_names:
        s = dim_scores[dim].score
        global_auc = (_auc(s[pr_mask], keeper[pr_mask]) if pr_mask.sum() else None)
        # within-stack AUC: pool per-stack pick/reject decisions
        ws_pairs, ws_correct = 0, 0
        for st in set(stack_of[pr_mask]):
            if st is None:
                continue
            sel = (stack_of == st) & pr_mask
            kp = s[sel][keeper[sel] == 1]
            rj = s[sel][reject[sel] == 1]
            for a in kp:
                for b in rj:
                    ws_pairs += 1
                    ws_correct += int(a > b)
        metrics["dimensions"][dim] = {
            "spearman_rating": _spearman(s, rating),
            "auc_pick_vs_reject": (round(global_auc, 4) if global_auc is not None else None),
            "within_stack_pairs": ws_pairs,
            "within_stack_concordance": (round(ws_correct / ws_pairs, 4) if ws_pairs else None),
            "score_mean_picked": (round(float(s[keeper == 1].mean()), 4) if keeper.sum() else None),
            "score_mean_rejected": (round(float(s[reject == 1].mean()), 4) if reject.sum() else None),
        }
    metrics["csv"] = str(csv_path)
    return metrics


# --------------------------------------------------------------------------- #
def _print_table(results: list[dict]) -> None:
    print("\n=== clip_quality_v0 — pick/reject separation by space "
          "(higher AUC/concordance = better) ===")
    print(f"{'space':28} {'n':>5} {'pick':>5} {'rej':>5} {'spear':>7} "
          f"{'AUC':>6} {'ws_conc':>8} {'mPick':>6} {'mRej':>6}")
    for r in results:
        d = r["dimensions"]["clip_quality_v0"]
        print(f"{r['space']:28} {r['n_images']:5d} {r['n_picked']:5d} "
              f"{r['n_rejected']:5d} {str(d['spearman_rating']):>7} "
              f"{str(d['auc_pick_vs_reject']):>6} "
              f"{str(d['within_stack_concordance']):>8} "
              f"{str(d['score_mean_picked']):>6} {str(d['score_mean_rejected']):>6}")


def _write_json(name: str, payload) -> Path:
    import json

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / name
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    logger.info("Wrote %s (%d bytes)", out, out.stat().st_size)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spaces", default="all",
                    help="comma list or 'all': " + ",".join(ALL_TEXT_SPACES))
    ap.add_argument("--folders", default="",
                    help="optional comma list of folder_id to restrict the corpus")
    ap.add_argument("--limit", type=int, default=None,
                    help="optional cap on number of images (debug)")
    ap.add_argument("--temp", type=float, default=100.0,
                    help="antonym-softmax temperature (CLIP logit scale ~100)")
    ap.add_argument("--out", default="",
                    help="output subdirectory under reports/clip-culling/prompt-quality/"
                         " (e.g. 'e2e' to avoid clobbering a prod run)")
    args = ap.parse_args(argv)

    global RESULTS_DIR
    if args.out:
        RESULTS_DIR = RESULTS_DIR / args.out

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s - %(levelname)s - %(message)s")

    from modules import db
    if db._get_db_engine() != "postgres":  # noqa: SLF001
        raise SystemExit("This benchmark requires database.engine = 'postgres'.")

    spaces = ALL_TEXT_SPACES if args.spaces == "all" else \
        [s.strip() for s in args.spaces.split(",") if s.strip()]
    unknown = [s for s in spaces if s not in ALL_TEXT_SPACES]
    if unknown:
        raise SystemExit(f"Unknown/text-incapable spaces: {unknown}; "
                         f"valid: {ALL_TEXT_SPACES}")
    folders = [int(x) for x in args.folders.split(",") if x.strip()] or None

    meta = load_meta(folders, args.limit)
    logger.info("Loaded meta for %d labeled images%s", len(meta),
                f" (folders {folders})" if folders else "")
    if not meta:
        raise SystemExit("No labeled images found for the given filter.")

    results = []
    for space in spaces:
        try:
            m = run_space(space, meta, args.temp, RESULTS_DIR, folders)
        except Exception as e:  # noqa: BLE001
            logger.exception("[%s] failed: %s", space, e)
            continue
        if m:
            results.append(m)

    if not results:
        logger.error("No spaces produced results (no persisted embeddings?).")
        return 1

    summary = {"prompt_set_version": PROMPT_SET_VERSION, "temp": args.temp,
               "templates": list(TEMPLATES), "n_meta": len(meta),
               "folders": folders, "results": results}
    _write_json("summary.json", summary)
    _print_table(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
