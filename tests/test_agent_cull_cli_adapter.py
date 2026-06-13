"""Tests for agent cull CLI adapter (mocked)."""

from dataclasses import replace
from unittest.mock import MagicMock, patch

from modules.agent_cull.cli_adapter import MockAgentCullProvider, SubprocessAgentCullProvider, build_prompt
from modules.agent_cull.config import AgentCullAgentConfig, AgentCullConfig


def test_mock_provider_returns_stdout():
    provider = MockAgentCullProvider('{"schema_version":"agent-cull-response-v1"}')
    cfg = AgentCullConfig()
    result = provider.run_review("prompt", cfg)
    assert result.ok is True
    assert "schema_version" in result.stdout


def test_build_prompt_includes_packet():
    packet = {"schema_version": "agent-cull-request-v1", "rejected_image_ids": [1]}
    prompt = build_prompt(packet)
    assert "agent-cull-request-v1" in prompt
    assert "Return JSON only" in prompt


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
