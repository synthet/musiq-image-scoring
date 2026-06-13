"""External CLI agent adapter for agent cull review."""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from modules.agent_cull.config import AgentCullConfig

logger = logging.getLogger(__name__)

MAX_RESPONSE_BYTES = 512_000


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
        return raw.exit_code != 0 and not (raw.stdout or "").strip()

    def _run_once(self, prompt: str, cfg: AgentCullConfig) -> AgentCullRawResponse:
        import time

        cmd = [self.command, *self.args]
        provider = cfg.agent.provider.lower()
        if provider == "gemini":
            cmd = [self.command, "--output-format", "json", "-p", prompt]
        elif provider == "codex":
            cmd = [self.command, "exec", "--sandbox", "read-only", "--ask-for-approval", "never", "--json", prompt]
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
            stdout = (proc.stdout or "")[:MAX_RESPONSE_BYTES]
            stderr = (proc.stderr or "")[:MAX_RESPONSE_BYTES]
            return AgentCullRawResponse(
                ok=proc.returncode == 0,
                stdout=stdout,
                stderr=stderr,
                exit_code=int(proc.returncode),
                duration_ms=duration_ms,
                provider=self.name,
                supports_vision=self.supports_vision,
                error=None if proc.returncode == 0 else f"exit_code_{proc.returncode}",
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
            return AgentCullRawResponse(
                ok=False,
                stdout="",
                stderr=str(exc),
                exit_code=-1,
                duration_ms=duration_ms,
                provider=self.name,
                supports_vision=self.supports_vision,
                error=str(exc),
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


def build_prompt(packet: dict[str, Any]) -> str:
    template_path = Path(__file__).resolve().parent / "prompts" / "cull_redundancy_v1.txt"
    template = template_path.read_text(encoding="utf-8")
    return template + "\n" + json.dumps(packet, ensure_ascii=False)


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
