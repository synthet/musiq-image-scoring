"""External CLI agent adapter for agent cull review."""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from modules.agent_cull.config import AgentCullConfig
from modules.agent_cull.json_util import json_dumps
from modules.agent_cull.mode_profiles import resolve_prompt_template_version
from modules.agent_cull.schema import extract_json_object

logger = logging.getLogger(__name__)

MAX_RESPONSE_BYTES = 512_000
AGENT_CLI_NOT_FOUND = "agent_cli_not_found"
_ANSI_ESCAPE = re.compile(r"\x1B\[[0-9;]*[A-Za-z]")


def normalize_gemini_stdout(stdout: str) -> str:
    """Unwrap Gemini CLI ``--output-format json`` envelope to agent payload text."""
    text = (stdout or "").strip()
    if not text:
        return text
    try:
        envelope = json.loads(text)
    except json.JSONDecodeError:
        return text
    if not isinstance(envelope, dict):
        return text
    inner = envelope.get("response")
    if isinstance(inner, str):
        return inner.strip()
    if isinstance(inner, dict):
        return json.dumps(inner, ensure_ascii=False)
    return text


def strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE.sub("", text or "")


def normalize_antigravity_stdout(stdout: str) -> str:
    """Strip terminal noise and return agent JSON payload text from agy -p output."""
    text = strip_ansi((stdout or "").strip())
    if not text:
        return text
    try:
        return extract_json_object(text)
    except ValueError:
        return normalize_gemini_stdout(text)


def classify_cli_process_failure(exit_code: int, stderr: str, *, stdout: str = "") -> tuple[str, str]:
    """Map non-zero CLI exit codes and stderr to stable operator-facing codes."""
    text = strip_ansi((stderr or "").strip())
    if not text:
        text = strip_ansi((stdout or "").strip())
    lower = text.lower()
    if (
        "authentication required" in lower
        or "authentication timed out" in lower
        or "waiting for authentication" in lower
        or "paste the authorization code" in lower
    ):
        return (
            "agent_cli_auth_failed",
            "Antigravity CLI is not authenticated in the WebUI process. Run agy once on the host "
            "(https://antigravity.google/download#antigravity-cli), mount credentials via "
            "GEMINI_CONFIG_SOURCE in .env, or set GEMINI_API_KEY / ANTIGRAVITY_API_KEY for the webui container.",
        )
    if "ineligibletiererror" in lower or "unsupported_client" in lower:
        return (
            "agent_cli_auth_tier",
            "Gemini CLI rejected this client tier. Re-authenticate or migrate to a supported "
            "Gemini/Antigravity plan, then restart the WebUI.",
        )
    if "error authenticating" in lower or "authentication failed" in lower:
        return (
            "agent_cli_auth_failed",
            "Gemini CLI authentication failed. Run `gemini auth` on the WebUI host (or refresh "
            "OAuth in Docker via GEMINI_CONFIG_SOURCE), then restart the WebUI.",
        )
    if "resource has been exhausted" in lower or "quota" in lower:
        return (
            "agent_cli_quota_exhausted",
            "Gemini CLI reported quota exhaustion. Check billing/limits or retry later.",
        )
    if "no such file or directory" in lower and "bash" in lower:
        return (
            "exit_code_127",
            "Agent bridge script has Windows CRLF line endings or a bad shebang. "
            "Run `git add --renormalize scripts/wsl/*.sh` and restart the WebUI container.",
        )
    if text:
        first_line = next((line.strip() for line in text.splitlines() if line.strip()), text)
        if len(first_line) > 240:
            first_line = first_line[:237] + "..."
        return f"exit_code_{exit_code}", first_line
    return f"exit_code_{exit_code}", f"Agent CLI exited with code {exit_code}."


def detect_cli_auth_failure(stdout: str, stderr: str) -> tuple[str, str] | None:
    """Detect auth prompts even when agy exits 0 after a headless OAuth timeout."""
    text = strip_ansi(f"{stderr or ''}\n{stdout or ''}").lower()
    if (
        "authentication required" in text
        or "authentication timed out" in text
        or "waiting for authentication" in text
        or "paste the authorization code" in text
        or "ineligibletiererror" in text
        or "unsupported_client" in text
        or "error authenticating" in text
        or "authentication failed" in text
    ):
        code, message = classify_cli_process_failure(1, stderr, stdout=stdout)
        if code.startswith("exit_code_"):
            return ("agent_cli_auth_failed", message)
        return code, message
    return None


def classify_cli_os_error(exc: OSError, command: str) -> tuple[str, str]:
    """Map subprocess spawn failures to stable operator-facing codes."""
    message = str(exc)
    errno = getattr(exc, "errno", None)
    missing = errno == 2 or "No such file or directory" in message
    if missing:
        return (
            AGENT_CLI_NOT_FOUND,
            f"Agent CLI not found: {command!r}. Install it and ensure it is on PATH "
            f"for the WebUI process, or set culling.agent_review.agent.command to the full path.",
        )
    return "agent_cli_spawn_failed", message


@dataclass
class AgentCullRawResponse:
    ok: bool
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    timed_out: bool = False
    provider: str = ""
    supports_vision: bool = False
    error: str | None = None


class AgentCullProvider(Protocol):
    name: str
    supports_vision: bool

    def run_review(self, prompt: str, cfg: AgentCullConfig) -> AgentCullRawResponse:
        ...


class MockAgentCullProvider:
    """Deterministic provider for tests."""

    name = "mock"
    supports_vision = True

    def __init__(self, response_text: str, *, exit_code: int = 0):
        self.response_text = response_text
        self.exit_code = exit_code

    def run_review(self, prompt: str, cfg: AgentCullConfig) -> AgentCullRawResponse:
        _ = prompt, cfg
        return AgentCullRawResponse(
            ok=self.exit_code == 0,
            stdout=self.response_text,
            stderr="",
            exit_code=self.exit_code,
            duration_ms=1,
            provider=self.name,
            supports_vision=self.supports_vision,
        )


class SubprocessAgentCullProvider:
    """Invoke a configured local CLI with JSON-only prompt (no shell=True)."""

    def __init__(self, *, name: str, command: str, args: tuple[str, ...], supports_vision: bool):
        self.name = name
        self.command = command
        self.args = args
        self.supports_vision = supports_vision

    @staticmethod
    def _is_transient_failure(raw: AgentCullRawResponse) -> bool:
        if raw.timed_out:
            return True
        haystack = f"{raw.error or ''} {raw.stderr or ''}".lower()
        if any(token in haystack for token in ("502", "503", "504", "timeout", "temporarily unavailable")):
            return True
        if any(
            token in haystack
            for token in (
                "agent_cli_auth_tier",
                "agent_cli_auth_failed",
                "agent_cli_quota_exhausted",
                "ineligibletiererror",
                "unsupported_client",
                "error authenticating",
                "authentication timed out",
                "waiting for authentication",
            )
        ):
            return False
        return raw.exit_code != 0 and not (raw.stdout or "").strip()

    def _run_once(self, prompt: str, cfg: AgentCullConfig) -> AgentCullRawResponse:
        import time

        cmd = [self.command, *self.args]
        provider = cfg.agent.provider.lower()
        if provider == "gemini":
            cmd = [self.command, "--skip-trust", "--output-format", "json", "-p", prompt]
        elif provider == "antigravity":
            cmd = [self.command, prompt]
        elif provider == "codex":
            sandbox = (cfg.agent.codex_sandbox or "read-only").strip() or "read-only"
            cmd = [
                self.command,
                "exec",
                "--sandbox",
                sandbox,
                "--ask-for-approval",
                "never",
                "--json",
                prompt,
            ]
        else:
            cmd = [self.command, *self.args, prompt]

        start = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=max(1, int(cfg.agent.timeout_seconds)),
                shell=False,
                check=False,
            )
            duration_ms = int((time.monotonic() - start) * 1000)
            raw_stdout = (proc.stdout or "")[:MAX_RESPONSE_BYTES]
            raw_stderr = (proc.stderr or "")[:MAX_RESPONSE_BYTES]
            auth_failure = detect_cli_auth_failure(raw_stdout, raw_stderr)
            if auth_failure:
                error_code, error_message = auth_failure
                return AgentCullRawResponse(
                    ok=False,
                    stdout=raw_stdout,
                    stderr=error_message,
                    exit_code=int(proc.returncode or 1),
                    duration_ms=duration_ms,
                    provider=self.name,
                    supports_vision=self.supports_vision,
                    error=error_code,
                )
            stdout = raw_stdout
            stderr = raw_stderr
            if provider == "gemini" and stdout:
                stdout = normalize_gemini_stdout(stdout)
            elif provider == "antigravity" and stdout:
                stdout = normalize_antigravity_stdout(stdout)
            error_code: str | None = None
            if proc.returncode != 0:
                error_code, _ = classify_cli_process_failure(
                    int(proc.returncode),
                    stderr,
                    stdout=stdout,
                )
            elif provider == "antigravity" and not stdout.strip():
                error_code, stderr = classify_cli_process_failure(1, stderr, stdout=stdout)
                return AgentCullRawResponse(
                    ok=False,
                    stdout=stdout,
                    stderr=stderr,
                    exit_code=1,
                    duration_ms=duration_ms,
                    provider=self.name,
                    supports_vision=self.supports_vision,
                    error=error_code,
                )
            return AgentCullRawResponse(
                ok=proc.returncode == 0,
                stdout=stdout,
                stderr=stderr,
                exit_code=int(proc.returncode),
                duration_ms=duration_ms,
                provider=self.name,
                supports_vision=self.supports_vision,
                error=error_code,
            )
        except subprocess.TimeoutExpired as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            partial = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
            if isinstance(exc.stdout, bytes):
                partial = exc.stdout.decode("utf-8", errors="replace")
            return AgentCullRawResponse(
                ok=False,
                stdout=str(partial)[:MAX_RESPONSE_BYTES],
                stderr="timeout",
                exit_code=-1,
                duration_ms=duration_ms,
                timed_out=True,
                provider=self.name,
                supports_vision=self.supports_vision,
                error="timeout",
            )
        except OSError as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            error_code, error_message = classify_cli_os_error(exc, self.command)
            return AgentCullRawResponse(
                ok=False,
                stdout="",
                stderr=error_message,
                exit_code=-1,
                duration_ms=duration_ms,
                provider=self.name,
                supports_vision=self.supports_vision,
                error=error_code,
            )

    def run_review(self, prompt: str, cfg: AgentCullConfig) -> AgentCullRawResponse:
        attempts = max(1, 1 + max(0, int(cfg.agent.max_retries)))
        last: AgentCullRawResponse | None = None
        for attempt in range(attempts):
            last = self._run_once(prompt, cfg)
            if last.ok:
                return last
            if attempt >= attempts - 1 or not self._is_transient_failure(last):
                return last
            logger.warning(
                "agent cull CLI transient failure (%s); retry %s/%s",
                last.error or last.stderr,
                attempt + 2,
                attempts,
            )
        return last  # pragma: no cover


def build_prompt(
    packet: dict[str, Any],
    cfg: AgentCullConfig | None = None,
    *,
    template_version: str | None = None,
) -> str:
    cfg = cfg or AgentCullConfig()
    version = resolve_prompt_template_version(cfg, override=template_version)
    prompts_dir = Path(__file__).resolve().parent / "prompts"
    template_path = prompts_dir / f"{version}.txt"
    if not template_path.is_file():
        raise FileNotFoundError(f"agent cull prompt template not found: {template_path}")
    template = template_path.read_text(encoding="utf-8")
    if cfg.review_picked_quality:
        snippet_path = prompts_dir / "picked_quality_audit_snippet.txt"
        if snippet_path.is_file():
            snippet = snippet_path.read_text(encoding="utf-8").strip()
            sentinel = "Review packet JSON follows:"
            if sentinel in template:
                template = template.replace(sentinel, snippet + "\n\n" + sentinel, 1)
            else:
                template = template.rstrip() + "\n\n" + snippet + "\n"
    return template + "\n" + json_dumps(packet)


def get_provider(cfg: AgentCullConfig, *, override: str | None = None) -> AgentCullProvider:
    provider_name = (override or cfg.agent.provider or "gemini").lower()
    if provider_name == "mock":
        raise ValueError("mock provider must be injected explicitly in tests")
    return SubprocessAgentCullProvider(
        name=provider_name,
        command=cfg.agent.command,
        args=cfg.agent.args,
        supports_vision=cfg.agent.supports_vision,
    )
