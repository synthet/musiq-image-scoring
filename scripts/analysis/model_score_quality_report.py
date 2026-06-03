#!/usr/bin/env python3
"""
Model score quality report — distribution, correlation, and diversity metrics.

Pulls normalized 0–1 scores from PostgreSQL (legacy ``images`` columns and
``image_model_scores``), computes histograms, pairwise correlations, and
quality/diversity summaries, then writes JSON + self-contained HTML (Chart.js).

Run in WSL with the app venv::

    source ~/.venvs/tf/bin/activate
    python scripts/analysis/model_score_quality_report.py
    python scripts/analysis/model_score_quality_report.py --folder-path "D:/Photos/2024"
    python scripts/analysis/model_score_quality_report.py --output-dir reports/model-score-quality/run1
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

project_root = str(Path(__file__).resolve().parents[2])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from modules import db  # noqa: E402
from modules.score_normalization import DEFAULT_PERCENTILE_ANCHORS  # noqa: E402

REPORT_VERSION = "1.0"

LEGACY_MODEL_COLUMNS: Dict[str, str] = {
    "liqe": "score_liqe",
    "ava": "score_ava",
    "spaq": "score_spaq",
    "koniq": "score_koniq",
    "paq2piq": "score_paq2piq",
}

COMPOSITE_COLUMNS: Dict[str, str] = {
    "general": "score_general",
    "technical": "score_technical",
    "aesthetic": "score_aesthetic",
}


def _wsl_path(path: str) -> str:
    p = path.replace("\\", "/")
    if len(p) >= 3 and p[1] == ":" and p[0].isalpha():
        return f"/mnt/{p[0].lower()}/{p[2:].lstrip('/')}"
    return p


def _folder_filter(folder_path: Optional[str], alias: str = "f") -> Tuple[str, List[Any]]:
    if not folder_path:
        return "", []
    target = _wsl_path(folder_path)
    return (
        f"AND ({alias}.path = ? OR {alias}.path LIKE ? OR {alias}.path LIKE ?)",
        [target, target + "/%", target + "\\%"],
    )


def _row_to_dict(row, cols: List[str]) -> dict:
    if isinstance(row, dict):
        return {str(k).lower(): v for k, v in row.items()}
    if hasattr(row, "keys"):
        return {str(k).lower(): row.get(k) for k in row.keys()}
    return dict(zip(cols, row))


def _rows_to_dicts(cursor) -> List[dict]:
    rows = cursor.fetchall()
    if not rows:
        return []
    cols = [d[0].lower() for d in cursor.description]
    return [_row_to_dict(row, cols) for row in rows]


def discover_models(
    conn,
    *,
    include_composites: bool = True,
    production_only: bool = False,
    min_count: int = 0,
) -> List[dict]:
    """Return model metadata dicts: name, source, is_composite, count."""
    c = conn.cursor()
    models: Dict[str, dict] = {}

    for name, col in LEGACY_MODEL_COLUMNS.items():
        c.execute(f"SELECT COUNT(*) AS cnt FROM images WHERE {col} IS NOT NULL")
        row = c.fetchone()
        cnt = int((row[0] if not isinstance(row, dict) else row.get("cnt") or row.get("CNT") or 0))
        models[name] = {
            "name": name,
            "source": "legacy_column",
            "column": col,
            "is_composite": False,
            "is_shadow_capable": False,
            "count": cnt,
        }

    if include_composites:
        for name, col in COMPOSITE_COLUMNS.items():
            c.execute(f"SELECT COUNT(*) AS cnt FROM images WHERE {col} IS NOT NULL")
            row = c.fetchone()
            cnt = int((row[0] if not isinstance(row, dict) else row.get("cnt") or row.get("CNT") or 0))
            models[name] = {
                "name": name,
                "source": "legacy_column",
                "column": col,
                "is_composite": True,
                "is_shadow_capable": False,
                "count": cnt,
            }

    shadow_clause = "AND is_shadow = FALSE" if production_only else ""
    try:
        c.execute(
            f"""
            SELECT model_name, COUNT(*) AS cnt
            FROM image_model_scores
            WHERE status = 'success' AND normalized IS NOT NULL
            {shadow_clause}
            GROUP BY model_name
            ORDER BY cnt DESC
            """
        )
        for row in _rows_to_dicts(c):
            name = str(row.get("model_name") or "").strip().lower()
            if not name:
                continue
            cnt = int(row.get("cnt") or 0)
            if name in LEGACY_MODEL_COLUMNS and name in models:
                models[name]["ims_count"] = cnt
                models[name]["is_shadow_capable"] = True
                continue
            models[name] = {
                "name": name,
                "source": "image_model_scores",
                "column": None,
                "is_composite": False,
                "is_shadow_capable": True,
                "count": cnt,
            }
    except Exception:
        pass

    result = [m for m in models.values() if m["count"] >= min_count]
    result.sort(key=lambda m: (-m["count"], m["name"]))
    return result


def fetch_score_frame(
    conn,
    model_meta: Sequence[dict],
    *,
    folder_path: Optional[str] = None,
    sample: int = 0,
    production_only: bool = False,
) -> Tuple[pd.DataFrame, int]:
    """Build aligned score DataFrame indexed by image_id; return (df, total_images)."""
    legacy_cols = {
        m["name"]: m["column"]
        for m in model_meta
        if m["source"] == "legacy_column" and m.get("column")
    }
    ims_models = [m["name"] for m in model_meta if m["source"] == "image_model_scores"]

    select_cols = ["i.id AS image_id"]
    for col in legacy_cols.values():
        select_cols.append(f"i.{col}")

    fsql, fparams = _folder_filter(folder_path, alias="f")
    limit_sql = ""
    params: List[Any] = list(fparams)
    if sample and sample > 0:
        limit_sql = " ORDER BY RANDOM() LIMIT ?"
        params.append(sample)

    query = f"""
        SELECT {", ".join(select_cols)}
        FROM images i
        LEFT JOIN folders f ON f.id = i.folder_id
        WHERE 1=1 {fsql}
        {limit_sql}
    """
    c = conn.cursor()
    c.execute(query, params)
    rows = _rows_to_dicts(c)
    total_images = len(rows)
    if not rows:
        return pd.DataFrame(), total_images

    df = pd.DataFrame(rows)
    df = df.rename(columns={"image_id": "id"})
    rename_map = {col: name for name, col in legacy_cols.items()}
    df = df.rename(columns=rename_map)
    df = df.set_index("id")

    if ims_models:
        ids = list(df.index)
        ims_frames: List[pd.DataFrame] = []
        batch_size = 5000
        shadow_clause = "AND ims.is_shadow = FALSE" if production_only else ""
        for start in range(0, len(ids), batch_size):
            batch = ids[start : start + batch_size]
            ph = ",".join(["?"] * len(batch))
            model_ph = ",".join(["?"] * len(ims_models))
            ims_params: List[Any] = list(batch) + list(ims_models)
            ims_query = f"""
                SELECT ims.image_id, ims.model_name, ims.normalized
                FROM image_model_scores ims
                WHERE ims.image_id IN ({ph})
                  AND ims.model_name IN ({model_ph})
                  AND ims.status = 'success'
                  AND ims.normalized IS NOT NULL
                  {shadow_clause}
            """
            c.execute(ims_query, ims_params)
            ims_rows = _rows_to_dicts(c)
            if ims_rows:
                ims_frames.append(pd.DataFrame(ims_rows))

        if ims_frames:
            ims_df = pd.concat(ims_frames, ignore_index=True)
            ims_df["model_name"] = ims_df["model_name"].str.lower()
            pivot = ims_df.pivot_table(
                index="image_id",
                columns="model_name",
                values="normalized",
                aggfunc="first",
            )
            for name in ims_models:
                if name in pivot.columns:
                    if name in df.columns:
                        df[name] = df[name].combine_first(pivot[name])
                    else:
                        df[name] = pivot[name]

    keep = [m["name"] for m in model_meta if m["name"] in df.columns]
    out = df[keep].copy()
    for col in out.columns:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out, total_images


def histogram(series: pd.Series, bins: int = 20) -> List[dict]:
    values = series.dropna().astype(float).values
    if len(values) == 0:
        width = 1.0 / bins
        return [
            {
                "bucket_start": round(i * width, 6),
                "bucket_end": round((i + 1) * width, 6),
                "count": 0,
            }
            for i in range(bins)
        ]
    counts, edges = np.histogram(values, bins=bins, range=(0.0, 1.0))
    out: List[dict] = []
    for i, count in enumerate(counts):
        out.append(
            {
                "bucket_start": round(float(edges[i]), 6),
                "bucket_end": round(float(edges[i + 1]), 6),
                "count": int(count),
            }
        )
    return out


def descriptive_stats(series: pd.Series, corpus_size: int) -> dict:
    values = series.dropna().astype(float)
    count = int(len(values))
    null_rate = round(1.0 - (count / corpus_size), 6) if corpus_size else 0.0
    if count == 0:
        return {
            "count": 0,
            "null_rate": null_rate,
            "mean": None,
            "median": None,
            "std": None,
            "min": None,
            "max": None,
            "p02": None,
            "p25": None,
            "p75": None,
            "p98": None,
            "iqr": None,
            "skew": None,
            "kurtosis": None,
            "effective_range": None,
            "cv": None,
        }

    arr = values.values
    p02, p25, p75, p98 = np.percentile(arr, [2, 25, 75, 98])
    mean = float(np.mean(arr))
    std = float(np.std(arr, ddof=1)) if count > 1 else 0.0
    return {
        "count": count,
        "null_rate": null_rate,
        "mean": round(mean, 6),
        "median": round(float(np.median(arr)), 6),
        "std": round(std, 6),
        "min": round(float(np.min(arr)), 6),
        "max": round(float(np.max(arr)), 6),
        "p02": round(float(p02), 6),
        "p25": round(float(p25), 6),
        "p75": round(float(p75), 6),
        "p98": round(float(p98), 6),
        "iqr": round(float(p75 - p25), 6),
        "skew": round(float(scipy_stats.skew(arr, bias=False)), 6) if count > 2 else 0.0,
        "kurtosis": round(float(scipy_stats.kurtosis(arr, bias=False)), 6) if count > 3 else 0.0,
        "effective_range": round(float(p98 - p02), 6),
        "cv": round(std / mean, 6) if mean else None,
    }


def pairwise_count_matrix(df: pd.DataFrame, labels: List[str]) -> List[List[int]]:
    n = len(labels)
    mat = [[0] * n for _ in range(n)]
    for i, a in enumerate(labels):
        for j, b in enumerate(labels):
            mat[i][j] = int(df[[a, b]].dropna().shape[0])
    return mat


def correlation_matrices(df: pd.DataFrame) -> dict:
    labels = [c for c in df.columns if df[c].notna().sum() >= 2]
    if len(labels) < 2:
        empty = {"labels": labels, "matrix": [], "pairwise_n": []}
        return {"pearson": empty, "spearman": empty}

    sub = df[labels]
    pearson = sub.corr(method="pearson", min_periods=2)
    spearman = sub.corr(method="spearman", min_periods=2)
    pairwise_n = pairwise_count_matrix(sub, labels)

    def _to_matrix(corr_df: pd.DataFrame) -> List[List[Optional[float]]]:
        mat: List[List[Optional[float]]] = []
        for row_label in labels:
            row_vals: List[Optional[float]] = []
            for col_label in labels:
                val = corr_df.loc[row_label, col_label]
                if pd.isna(val):
                    row_vals.append(None)
                else:
                    row_vals.append(round(float(val), 6))
            mat.append(row_vals)
        return mat

    return {
        "pearson": {
            "labels": labels,
            "matrix": _to_matrix(pearson),
            "pairwise_n": pairwise_n,
        },
        "spearman": {
            "labels": labels,
            "matrix": _to_matrix(spearman),
            "pairwise_n": pairwise_n,
        },
    }


def diversity_summary(
    model_stats: Dict[str, dict],
    correlation: dict,
    df: pd.DataFrame,
) -> dict:
    discrimination_rank = sorted(
        [
            {
                "model": name,
                "effective_range": st.get("effective_range"),
                "std": st.get("std"),
                "count": st.get("count"),
            }
            for name, st in model_stats.items()
            if st.get("effective_range") is not None
        ],
        key=lambda x: (x["effective_range"] or 0),
        reverse=True,
    )

    labels = correlation.get("pearson", {}).get("labels", [])
    matrix = correlation.get("pearson", {}).get("matrix", [])
    redundant_pairs: List[dict] = []
    orthogonal_pairs: List[dict] = []
    for i, a in enumerate(labels):
        for j, b in enumerate(labels):
            if j <= i:
                continue
            if i >= len(matrix) or j >= len(matrix[i]):
                continue
            r = matrix[i][j]
            if r is None:
                continue
            entry = {"a": a, "b": b, "pearson_r": r}
            if abs(r) >= 0.85:
                redundant_pairs.append(entry)
            if abs(r) <= 0.40:
                orthogonal_pairs.append({**entry, "note": "complementary"})

    redundant_pairs.sort(key=lambda x: abs(x["pearson_r"]), reverse=True)
    orthogonal_pairs.sort(key=lambda x: abs(x["pearson_r"]))

    rank_delta_vs_general: Dict[str, Optional[float]] = {}
    if "general" in df.columns and df["general"].notna().sum() >= 2:
        for col in df.columns:
            if col == "general":
                continue
            paired = df[[col, "general"]].dropna()
            if len(paired) < 2:
                rank_delta_vs_general[col] = None
                continue
            model_rank = paired[col].rank(method="average", ascending=False)
            gen_rank = paired["general"].rank(method="average", ascending=False)
            rank_delta_vs_general[col] = round(
                float(np.mean(np.abs(model_rank.values - gen_rank.values))), 6
            )

    anchor_drift: Dict[str, dict] = {}
    for model, anchors in DEFAULT_PERCENTILE_ANCHORS.items():
        st = model_stats.get(model, {})
        if not st or st.get("p02") is None:
            continue
        anchor_drift[model] = {
            "config_p02": anchors.get("p02"),
            "config_p98": anchors.get("p98"),
            "live_p02": st.get("p02"),
            "live_p98": st.get("p98"),
            "p02_delta": round(st["p02"] - anchors.get("p02", 0), 6),
            "p98_delta": round(st["p98"] - anchors.get("p98", 0), 6),
        }

    return {
        "discrimination_rank": discrimination_rank,
        "redundant_pairs": redundant_pairs,
        "orthogonal_pairs": orthogonal_pairs,
        "rank_delta_vs_general": rank_delta_vs_general,
        "anchor_drift": anchor_drift,
    }


def build_report(
    df: pd.DataFrame,
    model_meta: Sequence[dict],
    *,
    bins: int,
    filters: dict,
    total_images: int,
) -> dict:
    model_names = [m["name"] for m in model_meta if m["name"] in df.columns]
    meta_by_name = {m["name"]: m for m in model_meta}

    models_out: Dict[str, dict] = {}
    stats_out: Dict[str, dict] = {}
    scored_by_model: Dict[str, int] = {}

    for name in model_names:
        series = df[name]
        st = descriptive_stats(series, total_images)
        stats_out[name] = st
        scored_by_model[name] = st["count"]
        meta = meta_by_name.get(name, {})
        models_out[name] = {
            "source": meta.get("source", "unknown"),
            "is_composite": bool(meta.get("is_composite")),
            "count": st["count"],
            "stats": st,
            "histogram": histogram(series, bins=bins),
        }

    correlation = correlation_matrices(df[model_names] if model_names else df)
    diversity = diversity_summary(stats_out, correlation, df)

    return {
        "report_version": REPORT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "filters": filters,
        "corpus": {
            "total_images": total_images,
            "scored_images_by_model": scored_by_model,
        },
        "models": models_out,
        "correlation": correlation,
        "diversity": diversity,
    }


def _heatmap_color(value: Optional[float]) -> str:
    if value is None:
        return "#eee"
    v = max(-1.0, min(1.0, float(value)))
    if v >= 0:
        g = int(80 + 175 * v)
        return f"rgb(255,{255 - g // 2},{255 - g})"
    r = int(80 + 175 * abs(v))
    return f"rgb({255 - r},{255 - r // 2},255)"


def render_html(report: dict) -> str:
    report_json = json.dumps(report, indent=2)
    models = report.get("models", {})
    diversity = report.get("diversity", {})
    pearson = report.get("correlation", {}).get("pearson", {})
    labels = pearson.get("labels", [])
    matrix = pearson.get("matrix", [])

    hist_html = "\n".join(
        f'<div class="chart-card"><h3>{name}</h3>'
        f'<canvas id="hist-{name}" height="120"></canvas>'
        f'<p class="meta">n={data.get("count", 0)} · '
        f'effective_range={data.get("stats", {}).get("effective_range")} · '
        f'std={data.get("stats", {}).get("std")}</p></div>'
        for name, data in sorted(models.items())
    )

    heat_rows = []
    for i, row_label in enumerate(labels):
        cells = [f"<th>{row_label}</th>"]
        row_vals = matrix[i] if i < len(matrix) else []
        for j, val in enumerate(row_vals):
            cells.append(
                f'<td style="background:{_heatmap_color(val)}" '
                f'title="{row_label} vs {labels[j]}">'
                f"{val if val is not None else '—'}</td>"
            )
        heat_rows.append(f"<tr>{''.join(cells)}</tr>")

    rank_rows = "".join(
        f"<tr><td>{i + 1}</td><td>{r['model']}</td>"
        f"<td>{r.get('effective_range')}</td><td>{r.get('std')}</td></tr>"
        for i, r in enumerate(diversity.get("discrimination_rank", []))
    )

    redundant_rows = "".join(
        f"<tr><td>{p['a']}</td><td>{p['b']}</td><td>{p['pearson_r']}</td></tr>"
        for p in diversity.get("redundant_pairs", [])
    )

    filters = report.get("filters", {})
    corpus = report.get("corpus", {})
    no_corr_colspan = max(2, len(labels) + 1)
    folder_label = filters.get("folder_path") or "all"
    sample_label = filters.get("sample") or "full corpus"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Model Score Quality Report</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 1.5rem; color: #1a1a1a; }}
    h1, h2 {{ margin-top: 1.5rem; }}
    .cards {{ display: flex; flex-wrap: wrap; gap: 1rem; margin: 1rem 0; }}
    .card {{ background: #f5f5f5; padding: 1rem 1.25rem; border-radius: 8px; min-width: 160px; }}
    .charts {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 1rem; }}
    .chart-card {{ border: 1px solid #ddd; border-radius: 8px; padding: 1rem; }}
    .meta {{ font-size: 0.85rem; color: #555; }}
    table {{ border-collapse: collapse; font-size: 0.85rem; }}
    th, td {{ border: 1px solid #ccc; padding: 0.35rem 0.5rem; text-align: center; }}
    th {{ background: #eee; }}
    .guide td:first-child {{ font-weight: 600; text-align: left; }}
    details {{ margin: 1rem 0; }}
  </style>
</head>
<body>
  <h1>Model Score Quality Report</h1>
  <p>Generated: {report.get("generated_at", "")} · version {report.get("report_version", "")}</p>
  <div class="cards">
    <div class="card"><strong>Images</strong><br>{corpus.get("total_images", 0)}</div>
    <div class="card"><strong>Models</strong><br>{len(models)}</div>
    <div class="card"><strong>Folder</strong><br>{folder_label}</div>
    <div class="card"><strong>Sample</strong><br>{sample_label}</div>
  </div>

  <h2>Interpretation guide</h2>
  <table class="guide">
    <tr><td>Narrow effective_range</td><td>Low discrimination; percentile rescaling matters</td></tr>
    <tr><td>High skew (&gt;1)</td><td>Scores pile at one end; tune thresholds per corpus</td></tr>
    <tr><td>Pearson r &gt; 0.85</td><td>Redundant pair; ensemble weight may overlap</td></tr>
    <tr><td>Pearson r &lt; 0.40</td><td>Complementary signal; good for diversity</td></tr>
    <tr><td>Anchor drift</td><td>Live p02/p98 diverged from config percentile anchors</td></tr>
  </table>

  <h2>Discrimination rank</h2>
  <table>
    <tr><th>#</th><th>Model</th><th>Effective range (p98−p02)</th><th>Std dev</th></tr>
    {rank_rows or "<tr><td colspan='4'>No data</td></tr>"}
  </table>

  <h2>Redundant pairs (|Pearson r| ≥ 0.85)</h2>
  <table>
    <tr><th>Model A</th><th>Model B</th><th>Pearson r</th></tr>
    {redundant_rows or "<tr><td colspan='3'>None</td></tr>"}
  </table>

  <h2>Score distributions</h2>
  <div class="charts">{hist_html}</div>

  <h2>Pearson correlation</h2>
  <table>
    <tr><th></th>{"".join(f"<th>{lb}</th>" for lb in labels)}</tr>
    {''.join(heat_rows) or f"<tr><td colspan='{no_corr_colspan}'>No correlation data</td></tr>"}
  </table>

  <details>
    <summary>Spearman correlation</summary>
    <div id="spearman-table"></div>
  </details>

  <script type="application/json" id="report-data">{report_json}</script>
  <script>
    const report = JSON.parse(document.getElementById('report-data').textContent);
    const models = report.models || {{}};

    for (const [name, data] of Object.entries(models)) {{
      const el = document.getElementById('hist-' + name);
      if (!el) continue;
      const buckets = (data.histogram || []).map(b => b.bucket_start + '–' + b.bucket_end);
      const counts = (data.histogram || []).map(b => b.count);
      new Chart(el, {{
        type: 'bar',
        data: {{
          labels: buckets,
          datasets: [{{ label: 'Images', data: counts, backgroundColor: 'rgba(54, 162, 235, 0.6)' }}]
        }},
        options: {{
          responsive: true,
          plugins: {{ legend: {{ display: false }} }},
          scales: {{
            x: {{ title: {{ display: true, text: 'Score bucket (0–1)' }}, ticks: {{ maxRotation: 90, autoSkip: true, maxTicksLimit: 12 }} }},
            y: {{ title: {{ display: true, text: 'Image count' }}, beginAtZero: true }}
          }}
        }}
      }});
    }}

    (function renderSpearman() {{
      const sp = report.correlation?.spearman || {{}};
      const labels = sp.labels || [];
      const matrix = sp.matrix || [];
      if (!labels.length) return;
      let html = '<table><tr><th></th>';
      labels.forEach(lb => {{ html += '<th>' + lb + '</th>'; }});
      html += '</tr>';
      labels.forEach((rowLabel, i) => {{
        html += '<tr><th>' + rowLabel + '</th>';
        (matrix[i] || []).forEach(val => {{
          html += '<td>' + (val == null ? '—' : val) + '</td>';
        }});
        html += '</tr>';
      }});
      html += '</table>';
      document.getElementById('spearman-table').innerHTML = html;
    }})();
  </script>
</body>
</html>"""


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Model score quality report (distributions, correlation, diversity)"
    )
    parser.add_argument(
        "--output-dir",
        help="Output directory (default: reports/model-score-quality/<timestamp>)",
    )
    parser.add_argument("--bins", type=int, default=20, help="Histogram buckets on [0,1]")
    parser.add_argument("--folder-path", help="Restrict to folder tree")
    parser.add_argument("--sample", type=int, default=0, help="Random sample size (0 = all)")
    parser.add_argument(
        "--production-only",
        action="store_true",
        help="Exclude shadow rows from image_model_scores",
    )
    parser.add_argument(
        "--min-count",
        type=int,
        default=100,
        help="Drop models with fewer scored images",
    )
    parser.add_argument(
        "--include-composites",
        action="store_true",
        default=True,
        help="Include general/technical/aesthetic composites",
    )
    parser.add_argument(
        "--no-composites",
        action="store_false",
        dest="include_composites",
        help="Exclude composite scores",
    )
    parser.add_argument("--json-only", action="store_true", help="Write report.json only")
    parser.add_argument("--html-only", action="store_true", help="Write report.html only")
    return parser.parse_args(argv)


def _filter_models_in_scope(
    model_meta: Sequence[dict],
    df: pd.DataFrame,
    min_count: int,
) -> List[dict]:
    return [
        m
        for m in model_meta
        if m["name"] in df.columns and int(df[m["name"]].notna().sum()) >= min_count
    ]


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.output_dir or f"reports/model-score-quality/{ts}")
    out_dir.mkdir(parents=True, exist_ok=True)

    filters = {
        "folder_path": args.folder_path,
        "sample": args.sample,
        "production_only": args.production_only,
        "bins": args.bins,
        "min_count": args.min_count,
        "include_composites": args.include_composites,
    }

    conn = None
    try:
        conn = db.get_db()
    except Exception as exc:
        print(f"DB connection failed: {exc}", file=sys.stderr)
        return 1

    try:
        model_meta = discover_models(
            conn,
            include_composites=args.include_composites,
            production_only=args.production_only,
            min_count=0,
        )
        if not model_meta:
            print("No scored models found in database.", file=sys.stderr)
            return 1

        df, total_images = fetch_score_frame(
            conn,
            model_meta,
            folder_path=args.folder_path,
            sample=args.sample,
            production_only=args.production_only,
        )

        model_meta = _filter_models_in_scope(model_meta, df, args.min_count)
        if not model_meta:
            print("No models with sufficient scored images in scope.", file=sys.stderr)
            return 1

        report = build_report(
            df,
            model_meta,
            bins=args.bins,
            filters=filters,
            total_images=total_images,
        )

        write_json = not args.html_only
        write_html = not args.json_only

        if write_json:
            json_path = out_dir / "report.json"
            json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(f"Wrote {json_path}")

        if write_html:
            html_path = out_dir / "report.html"
            html_path.write_text(render_html(report), encoding="utf-8")
            print(f"Wrote {html_path}")

        redundant = report.get("diversity", {}).get("redundant_pairs", [])
        print(
            f"Corpus: {total_images} images, {len(report.get('models', {}))} models "
            f"({len(redundant)} redundant pairs)"
        )
    finally:
        if conn:
            conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
