"""Shared helpers for electron API routers."""

from __future__ import annotations

import logging
import sys

from modules.api import deps, state

logger = logging.getLogger(__name__)


def api_module():
    return sys.modules["modules.api"]


_control_job = deps.control_job
_control_stage = deps.control_stage
_control_step = deps.control_step
_http_for_transition_error = deps.http_for_transition_error
graceful_shutdown_processing = state.graceful_shutdown_processing
_stop_runner_for_phase = state._stop_runner_for_phase
_stop_runner_for_job_row = state._stop_runner_for_job_row
_join_runner_threads = state._join_runner_threads
