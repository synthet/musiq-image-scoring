"""Study mode profiles for agent cull review (carousel-pick aligned A/B)."""

from __future__ import annotations

from dataclasses import replace

from modules.agent_cull.config import PROMPT_TEMPLATE_VERSION, AgentCullConfig

STUDY_MODE_IDS = (
    "baseline_v2",
    "vision_strict",
    "score_first",
    "technical_focus",
    "clip_gate",
    "metadata_only",
)


def resolve_prompt_template_version(cfg: AgentCullConfig, *, override: str | None = None) -> str:
    if override:
        return override.strip()
    version = (cfg.agent.prompt_template_version or "").strip()
    return version or PROMPT_TEMPLATE_VERSION


def apply_mode_profile(cfg: AgentCullConfig, mode_id: str) -> AgentCullConfig:
    """Return a copy of *cfg* tuned for a named study mode."""
    mode = (mode_id or "").strip().lower()
    if not mode or mode == "baseline_v2":
        return replace(
            cfg,
            agent=replace(
                cfg.agent,
                prompt_template_version="cull_redundancy_v2",
                require_vision_evidence=False,
                include_thumbnails=True,
            ),
        )
    if mode == "vision_strict":
        return replace(
            cfg,
            agent=replace(
                cfg.agent,
                prompt_template_version="cull_redundancy_v3_vision_strict",
                require_vision_evidence=True,
                include_thumbnails=True,
            ),
        )
    if mode == "score_first":
        return replace(
            cfg,
            agent=replace(
                cfg.agent,
                prompt_template_version="cull_redundancy_v3_score_first",
                require_vision_evidence=False,
                include_thumbnails=True,
            ),
        )
    if mode == "technical_focus":
        return replace(
            cfg,
            agent=replace(
                cfg.agent,
                prompt_template_version="cull_redundancy_v3_technical_focus",
                require_vision_evidence=False,
                include_thumbnails=True,
                flatten_model_scores=("clip_quality_v0", "topiq", "liqe", "spaq"),
            ),
        )
    if mode == "clip_gate":
        return replace(
            cfg,
            agent=replace(
                cfg.agent,
                prompt_template_version="cull_redundancy_v3_clip_gate",
                require_vision_evidence=False,
                include_thumbnails=True,
                flatten_model_scores=("clip_quality_v0",),
            ),
        )
    if mode == "metadata_only":
        return replace(
            cfg,
            agent=replace(
                cfg.agent,
                prompt_template_version="cull_redundancy_v3_vision_strict",
                require_vision_evidence=True,
                include_thumbnails=False,
            ),
        )
    raise ValueError(f"unknown study mode: {mode_id!r}; expected one of {STUDY_MODE_IDS}")
