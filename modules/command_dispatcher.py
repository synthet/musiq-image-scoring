import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from modules.events import event_manager
from modules.phases import sort_phase_value_strings
from modules.run_modes import CANONICAL_RUN_MODE, resolve_run_mode_flags

logger = logging.getLogger(__name__)

Handler = Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]


class CommandDispatcher:
    """Dispatch inbound WebSocket commands to explicit action handlers."""

    def __init__(self):
        self._handlers: Dict[str, Handler] = {
            "submit_image": self._handle_submit_image,
            "submit_folder": self._handle_submit_folder,
            "start_clustering": self._handle_start_clustering,
            "get_status": self._handle_get_status,
            "ping": self._handle_ping,
        }
        self._scoring_runner = None
        self._tagging_runner = None
        self._clustering_runner = None

    def set_runners(self, scoring_runner=None, tagging_runner=None, clustering_runner=None):
        self._scoring_runner = scoring_runner
        self._tagging_runner = tagging_runner
        self._clustering_runner = clustering_runner

    def register(self, action: str, handler: Handler):
        self._handlers[action] = handler

    async def handle(self, websocket, message: Dict[str, Any]):
        request_id = None
        if isinstance(message, dict):
            request_id = message.get("request_id")

        if not isinstance(message, dict):
            await self._respond(websocket, request_id, False, error="Invalid command payload; expected JSON object")
            return

        action = message.get("action")
        if not action:
            await self._respond(websocket, request_id, False, error="Missing required field: action")
            return

        handler = self._handlers.get(action)
        if handler is None:
            await self._respond(websocket, request_id, False, error=f"Unknown action: {action}")
            return

        try:
            payload = message.get("data") or {}
            if not isinstance(payload, dict):
                raise ValueError("data must be an object")
            result = await handler(payload)
            await self._respond(websocket, request_id, True, data=result)
        except Exception as exc:
            logger.error("WebSocket command failed (action=%s): %s", action, exc)
            await self._respond(websocket, request_id, False, error=str(exc))

    async def _respond(self, websocket, request_id: Optional[str], success: bool, data: Optional[Dict[str, Any]] = None, error: Optional[str] = None):
        message: Dict[str, Any] = {
            "type": "command_response",
            "request_id": request_id,
            "success": success,
            "data": data or {},
        }
        if error:
            message["error"] = error
        await event_manager.send_to(websocket, message)

    async def _handle_submit_image(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._enqueue_submit(data, default_scope_type="file")

    async def _handle_submit_folder(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._enqueue_submit(data, default_scope_type="folder_recursive")

    async def _handle_start_clustering(self, data: Dict[str, Any]) -> Dict[str, Any]:
        clustered_data = dict(data)
        clustered_data["jobType"] = "cluster"
        clustered_data.setdefault("options", {})
        return self._enqueue_submit(clustered_data, default_scope_type="folder_recursive")

    async def _handle_get_status(self, _data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "scoring": self._runner_status(self._scoring_runner),
            "tagging": self._runner_status(self._tagging_runner),
            "clustering": self._runner_status(self._clustering_runner),
        }

    async def _handle_ping(self, _data: Dict[str, Any]) -> Dict[str, Any]:
        return {"message": "pong"}

    def _runner_status(self, runner) -> Dict[str, Any]:
        if runner is None:
            return {"available": False}
        raw = runner.get_status()
        if len(raw) >= 5:
            is_running, _log_text, status_message, current, total = raw[:5]
        elif len(raw) == 4:
            is_running, status_message, current, total = raw
        else:
            return {
                "available": True,
                "is_running": False,
                "status_message": "Unknown runner status shape",
                "progress": {"current": 0, "total": 0},
            }
        return {
            "available": True,
            "is_running": bool(is_running),
            "status_message": status_message,
            "progress": {"current": current, "total": total},
        }

    def _enqueue_submit(self, data: Dict[str, Any], default_scope_type: str) -> Dict[str, Any]:
        from modules import db

        target_paths = data.get("targetPaths") or data.get("target_paths") or []
        if not isinstance(target_paths, list) or not target_paths:
            raise ValueError("targetPaths must be a non-empty list")

        options = data.get("options") or {}
        if not isinstance(options, dict):
            raise ValueError("options must be an object")

        primary_path = str(target_paths[0])
        job_type_in = (data.get("jobType") or "score").strip().lower()
        job_type_map = {
            "score": ("scoring", "scoring", ["indexing", "metadata", "scoring"]),
            "tag": ("keywords", "tagging", ["keywords"]),
            "cluster": ("culling", "clustering", ["culling"]),
            "pipeline": ("scoring", "scoring", ["indexing", "metadata", "scoring", "keywords", "culling"]),
        }
        if job_type_in not in job_type_map:
            raise ValueError(f"Unsupported jobType: {job_type_in}")

        phase_code, enqueue_job_type, phases = job_type_map[job_type_in]
        phases = sort_phase_value_strings(list(phases))

        mode_flags = resolve_run_mode_flags(CANONICAL_RUN_MODE)
        payload = {
            "scope_type": data.get("scopeType") or default_scope_type,
            "scope_paths": target_paths,
            "input_path": primary_path,
            "run_mode": CANONICAL_RUN_MODE,
            "skip_done": mode_flags["skip_done"],
            "skip_existing": mode_flags["skip_existing"],
            "force_rerun": mode_flags["force_rerun"],
            "fix_incomplete_stages": mode_flags["fix_incomplete_stages"],
            "overwrite": mode_flags["overwrite"],
            "force_rescan": mode_flags["force_rescan"],
            "phases": phases,
            "target_phases": phases,
            "command_source": "websocket",
        }
        from modules.job_description import augment_queue_payload_for_audit, build_run_submit_description
        from modules.run_manifest import REASON_SOURCE_WEBSOCKET, attach_run_reason

        payload = augment_queue_payload_for_audit(payload, trigger="websocket", tool_id="command_dispatcher")
        payload = attach_run_reason(
            payload,
            source=REASON_SOURCE_WEBSOCKET,
            summary=f"WebSocket command queued {job_type_in} for {primary_path}.",
            trigger="websocket",
            tool_id="command_dispatcher",
            criteria={
                "job_type": job_type_in,
                "enqueued_phases": phases,
                "scope_paths": target_paths,
                "run_mode": CANONICAL_RUN_MODE,
            },
        )
        wf_desc = build_run_submit_description(
            scope_type=str(payload.get("scope_type") or "folder_recursive"),
            scope_paths=list(target_paths or []),
            run_mode=CANONICAL_RUN_MODE,
            phase_values=list(phases or []),
            client_description=None,
        )

        job_id, queue_position = db.enqueue_job_with_phases(
            primary_path,
            phase_code,
            enqueue_job_type,
            payload,
            wf_desc,
            phase_codes=phases,
            first_phase_state="queued",
        )
        if not job_id:
            raise RuntimeError("Failed to enqueue job")
        return {
            "job_id": job_id,
            "queue_position": queue_position,
            "job_type": enqueue_job_type,
            "input_path": primary_path,
        }


command_dispatcher = CommandDispatcher()
