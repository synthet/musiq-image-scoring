"""Tests for agent cull CLI adapter (mocked)."""

import json
from dataclasses import replace
from unittest.mock import MagicMock, patch

from modules.agent_cull.cli_adapter import (
    MockAgentCullProvider,
    SubprocessAgentCullProvider,
    build_prompt,
    classify_cli_process_failure,
    normalize_antigravity_stdout,
    normalize_gemini_stdout,
    normalize_result_envelope,
)
from modules.agent_cull.config import AgentCullAgentConfig, AgentCullConfig


def test_mock_provider_returns_stdout():
    provider = MockAgentCullProvider('{"schema_version":"agent-cull-response-v1"}')
    cfg = AgentCullConfig()
    result = provider.run_review("prompt", cfg)
    assert result.ok is True
    assert "schema_version" in result.stdout


def test_build_prompt_includes_packet():
    packet = {"schema_version": "agent-cull-request-v1", "rejected_image_ids": [1]}
    cfg = AgentCullConfig()
    prompt = build_prompt(packet, cfg)
    assert "agent-cull-request-v1" in prompt
    assert "Return JSON only" in prompt
    assert "thumbnail_manifest" in prompt
    assert "clip_quality_v0" in prompt


def test_subprocess_never_uses_shell():
    provider = SubprocessAgentCullProvider(
        name="gemini",
        command="echo",
        args=(),
        supports_vision=True,
    )
    cfg = AgentCullConfig()
    with patch("modules.agent_cull.cli_adapter.subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stdout = "{}"
        run.return_value.stderr = ""
        provider.run_review("{}", cfg)
        _, kwargs = run.call_args
        assert kwargs.get("shell") is False


def test_subprocess_timeout_marks_error():
    provider = SubprocessAgentCullProvider(
        name="gemini",
        command="sleep",
        args=(),
        supports_vision=True,
    )
    cfg = AgentCullConfig()
    with patch("modules.agent_cull.cli_adapter.subprocess.run") as run:
        import subprocess

        run.side_effect = subprocess.TimeoutExpired(cmd="sleep", timeout=1)
        result = provider.run_review("{}", cfg)
        assert result.ok is False
        assert result.timed_out is True


def test_subprocess_retries_transient_failures():
    provider = SubprocessAgentCullProvider(
        name="gemini",
        command="echo",
        args=(),
        supports_vision=True,
    )
    cfg = replace(AgentCullConfig(), agent=replace(AgentCullAgentConfig(), max_retries=1))
    with patch("modules.agent_cull.cli_adapter.subprocess.run") as run:
        run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr="503 Service Unavailable"),
            MagicMock(returncode=0, stdout='{"schema_version":"agent-cull-response-v1"}', stderr=""),
        ]
        result = provider.run_review("{}", cfg)
        assert result.ok is True
        assert run.call_count == 2


def test_subprocess_missing_cli_maps_agent_cli_not_found():
    provider = SubprocessAgentCullProvider(
        name="gemini",
        command="gemini",
        args=(),
        supports_vision=True,
    )
    cfg = AgentCullConfig()
    with patch("modules.agent_cull.cli_adapter.subprocess.run") as run:
        run.side_effect = FileNotFoundError(2, "No such file or directory", "gemini")
        result = provider.run_review("{}", cfg)
        assert result.ok is False
        assert result.error == "agent_cli_not_found"
        assert "gemini" in (result.stderr or "")


def test_subprocess_does_not_retry_when_stdout_present():
    provider = SubprocessAgentCullProvider(
        name="gemini",
        command="echo",
        args=(),
        supports_vision=True,
    )
    cfg = replace(AgentCullConfig(), agent=replace(AgentCullAgentConfig(), max_retries=2))
    with patch("modules.agent_cull.cli_adapter.subprocess.run") as run:
        run.return_value.returncode = 1
        run.return_value.stdout = '{"bad": true}'
        run.return_value.stderr = ""
        result = provider.run_review("{}", cfg)
        assert result.ok is False
        assert run.call_count == 1


def test_normalize_gemini_stdout_unwraps_envelope():
    envelope = '{"response": "{\\"schema_version\\": \\"agent-cull-response-v1\\"}", "stats": {}}'
    assert '"agent-cull-response-v1"' in normalize_gemini_stdout(envelope)


def test_classify_cli_process_failure_maps_auth_tier():
    stderr = (
        "Error authenticating: IneligibleTierError: unsupported client. "
        "Migrate to Antigravity."
    )
    code, message = classify_cli_process_failure(1, stderr)
    assert code == "agent_cli_auth_tier"
    assert "Antigravity" in message


def test_classify_cli_process_failure_maps_quota():
    code, _ = classify_cli_process_failure(1, "Resource has been exhausted (e.g. check quota).")
    assert code == "agent_cli_quota_exhausted"


def test_subprocess_maps_auth_tier_without_retry():
    provider = SubprocessAgentCullProvider(
        name="gemini",
        command="echo",
        args=(),
        supports_vision=True,
    )
    cfg = replace(AgentCullConfig(), agent=replace(AgentCullAgentConfig(), max_retries=2))
    with patch("modules.agent_cull.cli_adapter.subprocess.run") as run:
        run.return_value.returncode = 1
        run.return_value.stdout = ""
        run.return_value.stderr = "Error authenticating: IneligibleTierError: UNSUPPORTED_CLIENT"
        result = provider.run_review("{}", cfg)
        assert result.ok is False
        assert result.error == "agent_cli_auth_tier"
        assert run.call_count == 1


def test_classify_cli_process_failure_maps_antigravity_auth_timeout():
    stdout = "Waiting for authentication (timeout 30s)...\nError: authentication timed out."
    code, message = classify_cli_process_failure(0, "", stdout=stdout)
    assert code == "agent_cli_auth_failed"
    assert "Antigravity" in message


def test_subprocess_antigravity_auth_prompt_with_exit_zero():
    provider = SubprocessAgentCullProvider(
        name="antigravity",
        command="/app/scripts/wsl/antigravity_agent.sh",
        args=(),
        supports_vision=True,
    )
    cfg = replace(AgentCullConfig(), agent=replace(AgentCullAgentConfig(), provider="antigravity"))
    stdout = (
        "Authentication required. Please visit the URL to log in:\n"
        "Waiting for authentication (timeout 30s)...\n"
    )
    with patch("modules.agent_cull.cli_adapter.subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stdout = stdout
        run.return_value.stderr = ""
        result = provider.run_review("{}", cfg)
    assert result.ok is False
    assert result.error == "agent_cli_auth_failed"


def test_normalize_antigravity_stdout_extracts_json():
    raw = 'Here is the result:\n```json\n{"schema_version":"agent-cull-response-v1"}\n```'
    out = normalize_antigravity_stdout(raw)
    assert "agent-cull-response-v1" in out


def test_subprocess_antigravity_invokes_bridge_script_with_prompt():
    provider = SubprocessAgentCullProvider(
        name="antigravity",
        command="/app/scripts/wsl/antigravity_agent.sh",
        args=(),
        supports_vision=True,
    )
    cfg = replace(AgentCullConfig(), agent=replace(AgentCullAgentConfig(), provider="antigravity"))
    with patch("modules.agent_cull.cli_adapter.subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stdout = '{"schema_version":"agent-cull-response-v1"}'
        run.return_value.stderr = ""
        provider.run_review("{}", cfg)
        cmd_args, kwargs = run.call_args
        assert cmd_args[0] == ["/app/scripts/wsl/antigravity_agent.sh", "{}"]
        assert kwargs.get("shell") is False


def test_subprocess_gemini_unwraps_json_envelope():
    provider = SubprocessAgentCullProvider(
        name="gemini",
        command="echo",
        args=(),
        supports_vision=True,
    )
    cfg = AgentCullConfig()
    inner = '{"schema_version":"agent-cull-response-v1"}'
    wrapped = json.dumps({"response": inner, "session_id": "x"})
    with patch("modules.agent_cull.cli_adapter.subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stdout = wrapped
        run.return_value.stderr = ""
        result = provider.run_review("{}", cfg)
        assert result.ok is True
        assert result.stdout == inner


def test_normalize_result_envelope_unwraps():
    inner = '{"schema_version":"agent-cull-response-v1"}'
    wrapped = json.dumps({"type": "result", "subtype": "success", "result": inner})
    assert normalize_result_envelope(wrapped) == inner
    # Non-envelope text passes through unchanged.
    assert normalize_result_envelope(inner) == inner


def test_subprocess_claude_builds_print_json_cmd():
    provider = SubprocessAgentCullProvider(
        name="claude",
        command="/app/scripts/wsl/claude_agent.sh",
        args=(),
        supports_vision=True,
    )
    cfg = replace(AgentCullConfig(), agent=replace(AgentCullAgentConfig(), provider="claude"))
    with patch("modules.agent_cull.cli_adapter.subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stdout = '{"result":"{}"}'
        run.return_value.stderr = ""
        provider.run_review("{}", cfg)
        cmd_args, kwargs = run.call_args
        assert cmd_args[0] == [
            "/app/scripts/wsl/claude_agent.sh",
            "-p",
            "--output-format",
            "json",
            "--dangerously-skip-permissions",
            "{}",
        ]
        assert kwargs.get("shell") is False


def test_subprocess_cursor_builds_print_json_cmd():
    provider = SubprocessAgentCullProvider(
        name="cursor",
        command="/app/scripts/wsl/cursor_agent.sh",
        args=(),
        supports_vision=True,
    )
    cfg = replace(AgentCullConfig(), agent=replace(AgentCullAgentConfig(), provider="cursor"))
    with patch("modules.agent_cull.cli_adapter.subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stdout = '{"result":"{}"}'
        run.return_value.stderr = ""
        provider.run_review("{}", cfg)
        cmd_args, kwargs = run.call_args
        assert cmd_args[0] == [
            "/app/scripts/wsl/cursor_agent.sh",
            "-p",
            "--output-format",
            "json",
            "{}",
        ]
        assert kwargs.get("shell") is False


def test_subprocess_claude_unwraps_result_envelope():
    provider = SubprocessAgentCullProvider(
        name="claude",
        command="claude",
        args=(),
        supports_vision=True,
    )
    cfg = replace(AgentCullConfig(), agent=replace(AgentCullAgentConfig(), provider="claude"))
    inner = '{"schema_version":"agent-cull-response-v1"}'
    wrapped = json.dumps({"type": "result", "subtype": "success", "result": inner})
    with patch("modules.agent_cull.cli_adapter.subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stdout = wrapped
        run.return_value.stderr = ""
        result = provider.run_review("{}", cfg)
        assert result.ok is True
        assert result.stdout == inner
