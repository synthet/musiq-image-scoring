"""Safe output paths for side-effecting MCP actions."""

from __future__ import annotations

from pathlib import Path

from modules.mcp.actions.errors import PolicyError, ValidationError

_REPO_ROOT = Path(__file__).resolve().parents[3]

_BLOCKED_WRITE_PREFIXES = (
    _REPO_ROOT / "modules",
    _REPO_ROOT / "docs",
    _REPO_ROOT / "tests",
    _REPO_ROOT / "mcp",
    _REPO_ROOT / "frontend",
    _REPO_ROOT / "scripts",
    _REPO_ROOT / "migrations",
    _REPO_ROOT / "webui",
)


def validate_debug_bundle_output_path(
    output_path: str | None,
    *,
    repo_root: Path | None = None,
) -> Path | None:
    """Return resolved zip path or None for default safe directory."""
    root = repo_root or _REPO_ROOT
    if output_path is None or not str(output_path).strip():
        return None

    raw = str(output_path).strip()
    if ".." in Path(raw).parts:
        raise PolicyError(
            "output_path must not contain parent-directory segments",
            details={"output_path": raw, "policy": "path_traversal"},
        )

    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = (root / candidate).resolve()
    else:
        candidate = candidate.resolve()

    if candidate.suffix.lower() != ".zip":
        raise ValidationError(
            "output_path must end with .zip",
            details={"output_path": str(candidate)},
        )

    if candidate.exists():
        raise PolicyError(
            "output_path already exists; refusing to overwrite",
            details={"output_path": str(candidate), "policy": "no_overwrite"},
        )

    for blocked in _BLOCKED_WRITE_PREFIXES:
        try:
            candidate.relative_to(blocked.resolve())
            raise PolicyError(
                "output_path must not write into repository source directories",
                details={"output_path": str(candidate), "policy": "blocked_prefix"},
            )
        except ValueError:
            continue

    return candidate
