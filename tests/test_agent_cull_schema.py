"""Tests for agent cull response schema validation."""

import json

from modules.agent_cull.schema import validate_agent_response, validate_raw_agent_response


def _valid_response(*, stack_id=1, sub_stack_id=None, rejected=(10,), picked=(11,)):
    return {
        "schema_version": "agent-cull-response-v1",
        "stack_id": stack_id,
        "sub_stack_id": sub_stack_id,
        "group_decision": "apply_removals",
        "confidence": 0.9,
        "summary": "Near duplicates.",
        "rejected_image_decisions": [
            {
                "image_id": rejected[0],
                "filename": "a.jpg",
                "decision": "remove",
                "confidence": 0.92,
                "reason": "Blurrier duplicate.",
                "better_alternatives": [picked[0]],
                "risk_flags": [],
            }
        ],
    }


def test_valid_response():
    data = _valid_response()
    result = validate_agent_response(
        data,
        stack_id=1,
        sub_stack_id=None,
        rejected_image_ids={10},
        picked_image_ids={11},
    )
    assert result.ok is True


def test_malformed_json():
    result = validate_raw_agent_response(
        "not json",
        stack_id=1,
        sub_stack_id=None,
        rejected_image_ids={10},
        picked_image_ids={11},
    )
    assert result.ok is False
    assert result.error_code == "malformed_json"


def test_wrong_rejected_count():
    data = _valid_response()
    result = validate_agent_response(
        data,
        stack_id=1,
        sub_stack_id=None,
        rejected_image_ids={10, 12},
        picked_image_ids={11},
    )
    assert result.ok is False


def test_alternative_not_picked():
    data = _valid_response()
    data["rejected_image_decisions"][0]["better_alternatives"] = [99]
    result = validate_agent_response(
        data,
        stack_id=1,
        sub_stack_id=None,
        rejected_image_ids={10},
        picked_image_ids={11},
    )
    assert result.ok is False


def test_markdown_fenced_json_parses():
    inner = _valid_response()
    raw = "```json\n" + json.dumps(inner) + "\n```"
    result = validate_raw_agent_response(
        raw,
        stack_id=1,
        sub_stack_id=None,
        rejected_image_ids={10},
        picked_image_ids={11},
    )
    assert result.ok is True
