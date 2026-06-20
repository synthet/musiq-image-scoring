from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

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
