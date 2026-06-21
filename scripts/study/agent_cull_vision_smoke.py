#!/usr/bin/env python3
"""Direct CLI vision smoke: verify provider can read a thumbnail path."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _path_is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def _antigravity_cmd(prompt: str) -> list[str]:
    docker_agy = Path("/root/.local/bin/agy")
    if _path_is_file(docker_agy):
        return [str(docker_agy), "-p", prompt, "--dangerously-skip-permissions"]
    wsl_user = os.environ.get("USER") or os.environ.get("USERNAME")
    if wsl_user:
        win_agy = Path(f"/mnt/c/Users/{wsl_user}/AppData/Local/agy/bin/agy.exe")
        if _path_is_file(win_agy):
            return [str(win_agy), "-p", prompt, "--dangerously-skip-permissions"]
    win_home = os.environ.get("USERPROFILE") or ""
    if win_home:
        local = Path(win_home) / "AppData/Local/agy/bin/agy.exe"
        if _path_is_file(local):
            return [str(local), "-p", prompt, "--dangerously-skip-permissions"]
    for bridge in (Path("/app/scripts/wsl/antigravity_agent.sh"), ROOT / "scripts/wsl/antigravity_agent.sh"):
        if _path_is_file(bridge):
            return ["bash", str(bridge), prompt]
    return ["agy", "-p", prompt, "--dangerously-skip-permissions"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agent cull vision smoke test")
    parser.add_argument("image_path")
    parser.add_argument("provider", nargs="?", default="antigravity")
    parser.add_argument("image_id", nargs="?", type=int, default=0)
    args = parser.parse_args(argv)

    path = args.image_path
    provider = args.provider.lower()
    image_id = args.image_id

    if not os.path.isfile(path):
        print(json.dumps({"ok": False, "error": "path_not_found", "path": path}, indent=2))
        return 2

    prompt = (
        f"Read the image file at this exact path: {path}\n"
        "Reply with JSON only (no markdown): "
        f'{{"image_id": {image_id}, "species": "...", "focus_ok": true/false, '
        f'"blur_foreground": true/false, "visual_note": "one sentence"}}'
    )

    if provider == "antigravity":
        cmd = _antigravity_cmd(prompt)
    elif provider == "codex":
        sandbox = os.environ.get("CODEX_SANDBOX", "workspace")
        cmd = ["codex", "exec", "--sandbox", sandbox, "--ask-for-approval", "never", "--json", prompt]
    elif provider == "gemini":
        bridge = "/app/scripts/wsl/gemini_agent.sh"
        if os.path.isfile(bridge) and os.access(bridge, os.X_OK):
            cmd = [bridge, "--skip-trust", "-p", prompt]
        else:
            cmd = ["gemini", "--skip-trust", "--output-format", "json", "-p", prompt]
    else:
        print(json.dumps({"ok": False, "error": "unknown_provider", "provider": provider}, indent=2))
        return 2

    start = time.monotonic()
    timeout_s = int(os.environ.get("AGENT_CULL_SMOKE_TIMEOUT_S", "180"))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        duration = int(time.monotonic() - start)
        print(
            json.dumps(
                {
                    "ok": False,
                    "provider": provider,
                    "exit_code": -1,
                    "duration_s": duration,
                    "path": path,
                    "has_visual_language": False,
                    "error": "timeout",
                    "timeout_s": timeout_s,
                },
                indent=2,
            )
        )
        return 124
    duration = int(time.monotonic() - start)
    out = (proc.stdout or "") + (proc.stderr or "")
    visual_tokens = ("blur", "focus", "sharp", "soft", "deer", "fawn", "subject", "foreground", "background")
    lower = out.lower()
    result = {
        "ok": proc.returncode == 0,
        "provider": provider,
        "exit_code": proc.returncode,
        "duration_s": duration,
        "path": path,
        "has_visual_language": any(t in lower for t in visual_tokens),
        "stdout_head": (proc.stdout or "")[:2000],
        "stderr_head": (proc.stderr or "")[:500],
    }
    print(json.dumps(result, indent=2))
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
