"""Invoke canonical backend handlers for registry actions."""

from __future__ import annotations

import importlib
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def _resolve_callable(handler: dict[str, Any]) -> Callable[..., Any]:
    kind = handler.get("kind")
    module_name = handler.get("module")
    func_name = handler.get("function")
    if not module_name or not func_name:
        raise ValueError("Handler missing module or function")
    mod = importlib.import_module(str(module_name))
    fn = getattr(mod, str(func_name), None)
    if fn is None or not callable(fn):
        raise ValueError(f"Handler not callable: {module_name}.{func_name}")
    return fn


def invoke_handler(record: dict[str, Any], validated_args: dict[str, Any]) -> Any:
    handler = record.get("canonical_backend_handler") or {}
    action_id = record.get("action_id")
    fn = _resolve_callable(handler)

    if action_id == "diagnostics.run_doctor":
        include_gpu = not bool(validated_args.get("no_gpu", False))
        result = fn(include_gpu=include_gpu)
        if validated_args.get("json"):
            return {
                "overall": result.get("overall"),
                "failures": result.get("failures"),
                "warnings": result.get("warnings"),
                "database_engine_info": result.get("database_engine_info"),
            }
        from modules.doctor_cli import format_report

        return {"report": format_report(result), "overall": result.get("overall")}

    if action_id == "jobs.get_run_diagnostics":
        return fn(int(validated_args["run_id"]))

    if action_id == "jobs.get_job_details":
        return fn(int(validated_args["job_id"]))

    return fn(**validated_args) if validated_args else fn()
