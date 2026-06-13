"""Configuration for agent-assisted cull review."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from modules import config

PROMPT_TEMPLATE_VERSION = "cull_redundancy_v1"
RESPONSE_SCHEMA_VERSION = "agent-cull-response-v1"
REQUEST_SCHEMA_VERSION = "agent-cull-request-v1"


@dataclass(frozen=True)
class AgentCullAgentConfig:
    provider: str = "gemini"
    command: str = "gemini"
    args: tuple[str, ...] = ()
    timeout_seconds: int = 120
    max_retries: int = 1
    supports_vision: bool = True
    include_thumbnails: bool = True
    thumbnail_mode: str = "path"
    max_thumbnail_edge_px: int = 512


@dataclass(frozen=True)
class AgentCullLocalGatesConfig:
    block_if_rejected_scores_higher: bool = True
    score_margin: float = 0.0
    block_embedding_outliers: bool = True
    outlier_z_threshold: float = 2.0
    block_unique_species: bool = True
    block_unique_keywords: bool = True
    block_missing_alternatives: bool = True


@dataclass(frozen=True)
class AgentCullConfig:
    enabled: bool = False
    dry_run_default: bool = True
    max_group_size: int = 9
    min_usable_images: int = 2
    min_agent_confidence: float = 0.75
    min_group_confidence: float = 0.70
    decision_source: str = "pick_status"
    allow_metadata_only_remove: bool = False
    agent: AgentCullAgentConfig = field(default_factory=AgentCullAgentConfig)
    local_gates: AgentCullLocalGatesConfig = field(default_factory=AgentCullLocalGatesConfig)


def _coerce_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _coerce_float(value: Any, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_int(value: Any, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def load_agent_cull_config(overrides: dict[str, Any] | None = None) -> AgentCullConfig:
    """Load ``culling.agent_review`` from config.json with safe defaults."""
    section = config.get_config_section("culling") or {}
    raw = dict(section.get("agent_review") or {})
    if overrides:
        raw = {**raw, **overrides}

    agent_raw = dict(raw.get("agent") or {})
    gates_raw = dict(raw.get("local_gates") or {})
    args = agent_raw.get("args") or []
    if isinstance(args, list):
        args_tuple = tuple(str(a) for a in args)
    else:
        args_tuple = ()

    agent = AgentCullAgentConfig(
        provider=str(agent_raw.get("provider") or "gemini"),
        command=str(agent_raw.get("command") or "gemini"),
        args=args_tuple,
        timeout_seconds=_coerce_int(agent_raw.get("timeout_seconds"), 120),
        max_retries=_coerce_int(agent_raw.get("max_retries"), 1),
        supports_vision=_coerce_bool(agent_raw.get("supports_vision"), True),
        include_thumbnails=_coerce_bool(agent_raw.get("include_thumbnails"), True),
        thumbnail_mode=str(agent_raw.get("thumbnail_mode") or "path"),
        max_thumbnail_edge_px=_coerce_int(agent_raw.get("max_thumbnail_edge_px"), 512),
    )
    gates = AgentCullLocalGatesConfig(
        block_if_rejected_scores_higher=_coerce_bool(
            gates_raw.get("block_if_rejected_scores_higher"), True
        ),
        score_margin=_coerce_float(gates_raw.get("score_margin"), 0.0),
        block_embedding_outliers=_coerce_bool(gates_raw.get("block_embedding_outliers"), True),
        outlier_z_threshold=_coerce_float(gates_raw.get("outlier_z_threshold"), 2.0),
        block_unique_species=_coerce_bool(gates_raw.get("block_unique_species"), True),
        block_unique_keywords=_coerce_bool(gates_raw.get("block_unique_keywords"), True),
        block_missing_alternatives=_coerce_bool(gates_raw.get("block_missing_alternatives"), True),
    )
    return AgentCullConfig(
        enabled=_coerce_bool(raw.get("enabled"), False),
        dry_run_default=_coerce_bool(raw.get("dry_run_default"), True),
        max_group_size=_coerce_int(raw.get("max_group_size"), 9),
        min_usable_images=_coerce_int(raw.get("min_usable_images"), 2),
        min_agent_confidence=_coerce_float(raw.get("min_agent_confidence"), 0.75),
        min_group_confidence=_coerce_float(raw.get("min_group_confidence"), 0.70),
        decision_source=str(raw.get("decision_source") or "pick_status"),
        allow_metadata_only_remove=_coerce_bool(raw.get("allow_metadata_only_remove"), False),
        agent=agent,
        local_gates=gates,
    )
