from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

_ROOT = Path(__file__).resolve().parents[1]


def _run_worker_lines(lines: list[str]) -> list[dict]:
    script = _ROOT / "scripts" / "mcp" / "compact_worker.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        input="".join(line + "\n" for line in lines) + "__shutdown__\n",
        text=True,
        capture_output=True,
        cwd=_ROOT,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    out: list[dict] = []
    for raw in proc.stdout.splitlines():
        if raw.strip():
            out.append(json.loads(raw))
    return out


def test_worker_echoes_request_id_on_search():
    responses = _run_worker_lines(['{"id":"req-1","tool":"search","args":{"query":"health","limit":1}}'])
    assert len(responses) == 1
    assert responses[0]["_request_id"] == "req-1"
    assert "results" in responses[0]


def test_worker_parallel_requests_keep_distinct_ids():
    lines = [
        '{"id":"a","tool":"search","args":{"query":"health","limit":1}}',
        '{"id":"b","tool":"sse_status","args":{}}',
    ]
    responses = _run_worker_lines(lines)
    assert len(responses) == 2
    ids = {r["_request_id"] for r in responses}
    assert ids == {"a", "b"}


def test_dumps_response_serializes_datetime_and_decimal():
    import importlib.util

    worker_path = _ROOT / "scripts" / "mcp" / "compact_worker.py"
    spec = importlib.util.spec_from_file_location("compact_worker_under_test", worker_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    payload = {
        "status": "success",
        "data": {
            "created_at": datetime(2026, 7, 22, 12, 0, 0),
            "score": Decimal("1.25"),
            "id": UUID("00000000-0000-0000-0000-000000000001"),
        },
        "_request_id": "dt-1",
    }
    raw = mod.dumps_response(payload)
    parsed = json.loads(raw)
    assert parsed["data"]["created_at"] == "2026-07-22T12:00:00"
    assert parsed["data"]["score"] == 1.25
    assert parsed["data"]["id"] == "00000000-0000-0000-0000-000000000001"
    assert parsed["_request_id"] == "dt-1"


def test_worker_survives_after_search_when_prior_would_have_needed_datetime_codec():
    """Regression: json.dumps without default= crashed the process (exit 1)."""
    responses = _run_worker_lines(
        [
            '{"id":"s1","tool":"search","args":{"query":"error summary","limit":1}}',
            '{"id":"s2","tool":"search","args":{"query":"health","limit":1}}',
        ]
    )
    assert len(responses) == 2
    assert responses[0]["_request_id"] == "s1"
    assert responses[1]["_request_id"] == "s2"
