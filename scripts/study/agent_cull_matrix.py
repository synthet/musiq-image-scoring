#!/usr/bin/env python3
"""Agent cull CLI scoring & vision study matrix runner."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from modules.agent_cull.study_evidence import score_vision_evidence

ROOT = Path(__file__).resolve().parents[2]

DEFAULT_STACKS = (
    {"stack_id": 29157, "sub_stack_id": 72253, "label": "misfocus_fawn_195193"},
    {"stack_id": 29160, "sub_stack_id": None, "label": "deer_burst_agent_ok"},
    {"stack_id": 29154, "sub_stack_id": 72249, "label": "deer_burst_29154"},
)
# Historical fixture stack #28794 / sub 72076 is absent in current DB (auth-failure repro).

DEFAULT_MODES = (
    "baseline_v2",
    "vision_strict",
    "score_first",
    "technical_focus",
    "metadata_only",
)

DEFAULT_PROVIDERS = ("antigravity",)


def _detect_runtime() -> str:
    explicit = (os.environ.get("AGENT_CULL_STUDY_RUNTIME") or "").strip().lower()
    if explicit in ("docker", "wsl", "host"):
        return explicit
    if os.environ.get("DOCKER_CONTAINER") or os.path.exists("/.dockerenv"):
        return "docker"
    if sys.platform.startswith("linux") and "microsoft" in platform.uname().release.lower():
        return "wsl"
    return "host"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _wsl_project_root() -> str:
    """Map Windows project root to WSL mount path (e.g. D:\\Projects\\... → /mnt/d/Projects/...)."""
    drive = ROOT.drive.rstrip(":").lower()
    tail = ROOT.as_posix().split(":", 1)[-1]
    return f"/mnt/{drive}{tail}"


def _run_probe(stack_id: int, sub_stack_id: int | None, mode: str, runtime: str) -> dict[str, Any]:
    if runtime == "host" and sys.platform == "win32":
        wsl_root = _wsl_project_root()
        probe_args = [
            "scripts/study/agent_cull_probe.py",
            "--stack-id",
            str(stack_id),
            "--mode-profile",
            mode,
            "--runtime",
            runtime,
        ]
        if sub_stack_id is not None:
            probe_args.extend(["--sub-stack-id", str(sub_stack_id)])
        fb_lib = (
            f"{wsl_root}/FirebirdLinux/Firebird-5.0.0.1306-0-linux-x64/opt/firebird/lib"
        )
        bash_cmd = (
            f"cd {wsl_root} && source ~/.venvs/tf/bin/activate && "
            f"export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:{fb_lib} && "
            f"PYTHONPATH=. python {' '.join(probe_args)}"
        )
        proc = subprocess.run(
            ["wsl", "-e", "bash", "-lc", bash_cmd],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            check=False,
        )
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            data = {
                "ok": False,
                "parse_error": True,
                "stdout": proc.stdout[:2000],
                "stderr": proc.stderr[:1000],
                "delegated_via": "wsl",
            }
        data["_exit_code"] = proc.returncode
        return data

    cmd = [
        sys.executable,
        str(ROOT / "scripts/study/agent_cull_probe.py"),
        "--stack-id",
        str(stack_id),
        "--mode-profile",
        mode,
        "--runtime",
        runtime,
    ]
    if sub_stack_id is not None:
        cmd.extend(["--sub-stack-id", str(sub_stack_id)])
    env = {**os.environ, "AGENT_CULL_STUDY_RUNTIME": runtime}
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), env=env, check=False)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        data = {"ok": False, "parse_error": True, "stdout": proc.stdout[:2000], "stderr": proc.stderr[:1000]}
    data["_exit_code"] = proc.returncode
    return data


def _run_vision_smoke(path: str, provider: str, image_id: int, runtime: str) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(ROOT / "scripts/study/agent_cull_vision_smoke.py"),
        path,
        provider,
        str(image_id),
    ]
    env = {**os.environ, "AGENT_CULL_STUDY_RUNTIME": runtime}
    if provider == "codex":
        env.setdefault("CODEX_SANDBOX", "workspace")
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), env=env, check=False)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        data = {
            "ok": False,
            "stdout_head": proc.stdout[:2000],
            "stderr_head": proc.stderr[:1000],
        }
    data["_exit_code"] = proc.returncode
    return data


def _provider_command(provider: str):
    from modules.agent_cull.config import AgentCullAgentConfig, AgentCullConfig, load_agent_cull_config

    cfg = load_agent_cull_config()
    agent = cfg.agent
    if provider == "antigravity":
        cmd = agent.command if "antigravity" in agent.command else "/app/scripts/wsl/antigravity_agent.sh"
        agent = replace(agent, provider="antigravity", command=cmd)
    elif provider == "gemini":
        cmd = agent.command if "gemini" in agent.command else "gemini"
        agent = replace(agent, provider="gemini", command=cmd)
    elif provider == "codex":
        agent = replace(agent, provider="codex", command="codex", codex_sandbox="workspace")
    else:
        raise ValueError(f"unknown provider: {provider}")
    return provider, replace(cfg, enabled=True, agent=agent)


def _run_live_review(
    stack_id: int,
    sub_stack_id: int | None,
    mode: str,
    provider: str,
) -> dict[str, Any]:
    from modules.agent_cull.config import load_agent_cull_config
    from modules.agent_cull.discovery_db import inspect_review_unit_for_run, load_unit_rows
    from modules.agent_cull.mode_profiles import apply_mode_profile
    from modules.agent_cull.repository import get_review_group
    from modules.agent_cull.service import run_agent_review_for_unit

    _, cfg = _provider_command(provider)
    cfg = apply_mode_profile(cfg, mode)
    unit = inspect_review_unit_for_run(cfg, stack_id=stack_id, sub_stack_id=sub_stack_id)
    if unit is None:
        return {"ok": False, "error": "no_unit"}
    rows = load_unit_rows(unit)
    start = time.monotonic()
    outcome = run_agent_review_for_unit(
        unit,
        rows,
        cfg,
        dry_run=True,
        provider_override=provider,
    )
    duration_ms = int((time.monotonic() - start) * 1000)
    result: dict[str, Any] = {"duration_ms": duration_ms, **outcome}
    group_id = outcome.get("group_id")
    if group_id:
        group = get_review_group(int(group_id)) or {}
        response = group.get("response_validated") or {}
        request = group.get("request_json") or {}
        if isinstance(request, str):
            request = json.loads(request)
        if isinstance(response, str):
            response = json.loads(response)
        result["vision_used"] = response.get("vision_used")
        result["viewed_image_ids"] = response.get("viewed_image_ids")
        result["manifest_count"] = len(request.get("thumbnail_manifest") or [])
        result["decisions"] = {
            str(d.get("image_id")): d.get("decision")
            for d in (response.get("rejected_image_decisions") or [])
        }
    return result


def _write_summary_md(out_dir: Path, artifacts: list[dict[str, Any]]) -> None:
    lines = [
        "# Agent cull CLI matrix summary",
        "",
        f"Generated: {_utc_now()}",
        "",
        "| stack | mode | provider | runtime | manifest_ok | smoke_visual | vision_used | verified |",
        "|-------|------|----------|---------|-------------|--------------|-------------|----------|",
    ]
    for art in artifacts:
        probe = art.get("probe") or {}
        smoke = art.get("vision_smoke")
        live = art.get("live_review")
        ev = art.get("vision_evidence") or {}
        lines.append(
            "| {stack} | {mode} | {provider} | {runtime} | {mo} | {sv} | {vu} | {ver} |".format(
                stack=art.get("stack_label", art.get("stack_id")),
                mode=art.get("mode"),
                provider=art.get("provider"),
                runtime=art.get("runtime"),
                mo=probe.get("ok"),
                sv=(smoke or {}).get("has_visual_language"),
                vu=(live or {}).get("vision_used"),
                ver=ev.get("verified"),
            )
        )
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agent cull CLI study matrix")
    parser.add_argument("--output", type=Path, default=ROOT / ".agent/study/runs" / datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--stacks-json", help="JSON array of {stack_id, sub_stack_id, label}")
    parser.add_argument("--stacks-file", type=Path, help="Path to JSON stacks array (alternative to --stacks-json)")
    parser.add_argument("--modes", default=",".join(DEFAULT_MODES))
    parser.add_argument("--providers", default=",".join(DEFAULT_PROVIDERS))
    parser.add_argument("--runtimes", default="wsl")
    parser.add_argument("--skip-vision-smoke", action="store_true")
    parser.add_argument("--skip-live-cli", action="store_true", help="Preflight + smoke only (no LLM review)")
    parser.add_argument("--live-modes", default="baseline_v2,vision_strict", help="Modes that trigger live CLI when not skipped")
    args = parser.parse_args(argv)

    stacks = DEFAULT_STACKS
    if args.stacks_file:
        stacks = json.loads(args.stacks_file.read_text(encoding="utf-8"))
    elif args.stacks_json:
        stacks = json.loads(args.stacks_json)
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    providers = [p.strip() for p in args.providers.split(",") if p.strip()]
    runtimes = [r.strip() for r in args.runtimes.split(",") if r.strip()]
    live_modes = {m.strip() for m in args.live_modes.split(",") if m.strip()}

    out_dir = args.output
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "generated_at": _utc_now(),
        "modes": modes,
        "providers": providers,
        "runtimes": runtimes,
        "stacks": stacks,
        "skip_live_cli": args.skip_live_cli,
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    artifacts: list[dict[str, Any]] = []
    smoke_cache: dict[tuple[int, str, str], dict[str, Any] | None] = {}
    for stack in stacks:
        stack_id = int(stack["stack_id"])
        sub_stack_id = stack.get("sub_stack_id")
        if sub_stack_id is not None:
            sub_stack_id = int(sub_stack_id)
        label = stack.get("label") or str(stack_id)
        for runtime in runtimes:
            os.environ["AGENT_CULL_STUDY_RUNTIME"] = runtime
            for mode in modes:
                probe = _run_probe(stack_id, sub_stack_id, mode, runtime)
                artifact: dict[str, Any] = {
                    "stack_id": stack_id,
                    "sub_stack_id": sub_stack_id,
                    "stack_label": label,
                    "mode": mode,
                    "runtime": runtime,
                    "probe": probe,
                }
                smoke = None
                live = None
                manifest_sample = probe.get("manifest_sample") or {}
                smoke_path = manifest_sample.get("path")
                smoke_id = manifest_sample.get("image_id") or 0
                smoke_key = (stack_id, runtime, providers[0] if providers else "")
                if smoke_key in smoke_cache:
                    smoke = smoke_cache[smoke_key]
                elif (
                    not args.skip_vision_smoke
                    and smoke_path
                    and probe.get("include_thumbnails", True)
                    and probe.get("ok")
                ):
                    for provider in providers:
                        smoke = _run_vision_smoke(str(smoke_path), provider, int(smoke_id), runtime)
                        smoke_cache[smoke_key] = smoke
                        artifact["provider"] = provider
                        artifact["vision_smoke"] = smoke
                        break
                elif smoke_key in smoke_cache and smoke_cache[smoke_key] is not None:
                    smoke = smoke_cache[smoke_key]
                    artifact["vision_smoke"] = smoke
                if smoke is not None and "vision_smoke" not in artifact:
                    artifact["vision_smoke"] = smoke
                if (
                    not args.skip_vision_smoke
                    and smoke is None
                    and smoke_key not in smoke_cache
                ):
                    smoke_cache[smoke_key] = None
                if not artifact.get("provider") and providers:
                    artifact["provider"] = providers[0]
                if not args.skip_live_cli and mode in live_modes and artifact.get("provider"):
                    try:
                        live = _run_live_review(stack_id, sub_stack_id, mode, artifact["provider"])
                    except Exception as exc:
                        live = {"ok": False, "error": str(exc)}
                    artifact["live_review"] = live
                artifact["vision_evidence"] = score_vision_evidence(probe, smoke, live)
                slug = f"{label}_{mode}_{artifact.get('provider','na')}_{runtime}"
                (out_dir / f"{slug}.json").write_text(json.dumps(artifact, indent=2, default=str), encoding="utf-8")
                artifacts.append(artifact)

    (out_dir / "artifacts.json").write_text(json.dumps(artifacts, indent=2, default=str), encoding="utf-8")
    _write_summary_md(out_dir, artifacts)
    print(json.dumps({"output_dir": str(out_dir), "artifact_count": len(artifacts)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
