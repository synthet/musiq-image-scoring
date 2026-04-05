"""
Build manifest.json (+ optional README) for the Nikon NEF testing samples tree.

SHA-256 for every .NEF; optional ExifTool JSON for Nikon RAW tags.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from nef_testing_samples_sources import source_url_by_relpath

README_TEMPLATE_NAME = "NEF_TESTING_SAMPLES_README.md"


def _script_dir() -> Path:
    return Path(__file__).resolve().parent


def _repo_root() -> Path:
    return _script_dir().parents[1]


def _manifest_root_field(root: Path) -> str:
    root = root.resolve()
    try:
        return root.relative_to(_repo_root()).as_posix()
    except ValueError:
        return str(root)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def exiftool_available() -> bool:
    return shutil.which("exiftool") is not None


def read_exiftool_tags(path: Path) -> dict:
    cmd = [
        "exiftool",
        "-json",
        "-Make",
        "-Model",
        "-BitsPerSample",
        "-Compression",
        "-NEFCompression",
        "-ImageSize",
        str(path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"ExifToolError": str(e)}
    if proc.returncode != 0:
        return {"ExifToolError": (proc.stderr or proc.stdout or "exiftool failed").strip()}
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        return {"ExifToolError": f"invalid JSON: {e}"}
    return data[0] if data else {}


def collect_nef_paths(root: Path) -> list[Path]:
    seen: set[Path] = set()
    out: list[Path] = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() == ".nef":
            key = p.resolve()
            if key not in seen:
                seen.add(key)
                out.append(p)
    return sorted(out, key=lambda x: str(x).lower())


def build_manifest(root: Path, *, use_exiftool: bool) -> dict:
    root = root.resolve()
    url_map = source_url_by_relpath()
    et_ok = use_exiftool and exiftool_available()
    files: list[dict] = []

    for path in collect_nef_paths(root):
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            rel = str(path)
        entry: dict = {
            "path": rel,
            "sha256": sha256_file(path),
            "source_url": url_map.get(rel),
            "size_bytes": path.stat().st_size,
        }
        if use_exiftool:
            if et_ok:
                tags = read_exiftool_tags(path)
                for k in ("Make", "Model", "BitsPerSample", "Compression", "NEFCompression", "ImageSize"):
                    if k in tags:
                        entry[k] = tags[k]
                if "ExifToolError" in tags:
                    entry["ExifToolError"] = tags["ExifToolError"]
            else:
                entry["ExifToolSkipped"] = "exiftool not found on PATH"

        files.append(entry)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": _manifest_root_field(root),
        "exiftool_used": bool(et_ok),
        "files": files,
    }


def write_manifest_json(root: Path, data: dict) -> Path:
    root = root.resolve()
    out = root / "manifest.json"
    out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return out


def write_samples_readme(root: Path, *, force: bool = False) -> Path | None:
    root = root.resolve()
    dest = root / "README.md"
    if dest.exists() and not force:
        return None
    template = _script_dir() / README_TEMPLATE_NAME
    if not template.is_file():
        return None
    shutil.copyfile(template, dest)
    return dest


def refresh_testing_samples_artifacts(
    root: Path,
    *,
    use_exiftool: bool = True,
    write_readme_if_missing: bool = True,
    force_readme: bool = False,
) -> tuple[Path, Path | None, dict]:
    """Writes manifest.json; copies README from template if missing (or force)."""
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    data = build_manifest(root, use_exiftool=use_exiftool)
    mp = write_manifest_json(root, data)
    rp: Path | None = None
    if write_readme_if_missing or force_readme:
        rp = write_samples_readme(root, force=force_readme)
    return mp, rp, data
