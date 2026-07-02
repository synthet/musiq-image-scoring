"""Service batching for oversized agent-cull review units."""

import json
from unittest.mock import patch

from modules.agent_cull.cli_adapter import AgentCullProvider, AgentCullRawResponse
from modules.agent_cull.config import AgentCullConfig
from modules.agent_cull.discovery import ReviewUnit
from modules.agent_cull.service import run_agent_review_for_unit


class _BatchAwareMockProvider(AgentCullProvider):
    name = "mock"
    supports_vision = True

    def __init__(self):
        self.call_count = 0

    def run_review(self, prompt: str, cfg: AgentCullConfig) -> AgentCullRawResponse:
        self.call_count += 1
        _ = prompt, cfg
        # Parser in tests does not inspect prompt; validation uses unit rejected ids per batch.
        return AgentCullRawResponse(
            ok=True,
            stdout=json.dumps(
                {
                    "schema_version": "agent-cull-response-v1",
                    "stack_id": 1,
                    "sub_stack_id": 2,
                    "group_decision": "do_not_apply",
                    "confidence": 0.85,
                    "summary": "ok",
                    "vision_used": True,
                    "viewed_image_ids": [],
                    "rejected_image_decisions": [],
                }
            ),
            stderr="",
            exit_code=0,
            duration_ms=1,
            provider=self.name,
            supports_vision=True,
        )


def _make_unit(n: int) -> ReviewUnit:
    ids = tuple(range(1, n + 1))
    picked = ids[:2]
    rejected = ids[2:]
    return ReviewUnit(
        stack_id=1,
        sub_stack_id=2,
        review_unit_key="stack:1:sub:2",
        image_ids=ids,
        picked_ids=picked,
        rejected_ids=rejected,
        neutral_ids=(),
        usable_ids=ids,
        hierarchy_tier="single_leaf",
    )


def _rows(n: int) -> dict:
    return {
        i: {"id": i, "file_path": f"/tmp/{i}.jpg", "pick_status": 1 if i <= 2 else -1, "score_general": float(n - i)}
        for i in range(1, n + 1)
    }


def test_batched_review_runs_multiple_agent_calls():
    unit = _make_unit(25)
    rows = _rows(25)
    cfg = AgentCullConfig(
        dry_run_default=True,
        review_batch_size=10,
        review_picked_quality=False,
    )
    provider = _BatchAwareMockProvider()

    def _fake_validate(raw, **kwargs):
        rejected = kwargs.get("rejected_image_ids") or set()
        from modules.agent_cull.schema import ValidationResult

        decisions = [
            {
                "image_id": iid,
                "decision": "keep",
                "confidence": 0.8,
                "better_alternatives": [1],
                "reason": "ok",
            }
            for iid in sorted(rejected)
        ]
        return ValidationResult(
            ok=True,
            data={
                "schema_version": "agent-cull-response-v1",
                "stack_id": 1,
                "sub_stack_id": 2,
                "group_decision": "do_not_apply",
                "confidence": 0.85,
                "summary": "ok",
                "vision_used": True,
                "viewed_image_ids": list(rejected),
                "rejected_image_decisions": decisions,
            },
        )

    with (
        patch("modules.agent_cull.service.build_prompt", return_value="prompt"),
        patch("modules.agent_cull.service.validate_raw_agent_response", side_effect=_fake_validate),
        patch("modules.agent_cull.service.persist_validated_review", return_value=42) as persist,
    ):
        result = run_agent_review_for_unit(unit, rows, cfg=cfg, provider=provider)
    assert result["ok"] is True
    assert result["batch_count"] == 3
    assert provider.call_count == 3
    persist.assert_called_once()
    packet = persist.call_args.kwargs["packet"]
    assert packet.get("review_batches") == 3
