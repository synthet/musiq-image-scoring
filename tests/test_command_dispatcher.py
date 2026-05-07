import asyncio
import json
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from modules.command_dispatcher import CommandDispatcher
from modules.phases import sort_phase_value_strings
from modules.events import event_manager


class _FakeWebSocket:
    def __init__(self):
        self.messages = []

    async def send_text(self, text: str):
        self.messages.append(json.loads(text))


@pytest.fixture(autouse=True)
def _reset_connections():
    event_manager.active_connections.clear()
    yield
    event_manager.active_connections.clear()


def _make_ws_app(dispatcher: CommandDispatcher):
    @asynccontextmanager
    async def lifespan(_app):
        loop = asyncio.get_running_loop()
        event_manager.set_loop(loop)
        yield

    app = FastAPI(lifespan=lifespan)

    @app.websocket("/ws/updates")
    async def websocket_endpoint(websocket: WebSocket):
        await event_manager.connect(websocket)
        try:
            while True:
                data = await websocket.receive_text()
                try:
                    msg = json.loads(data)
                except json.JSONDecodeError:
                    await event_manager.send_to(
                        websocket,
                        {
                            "type": "command_response",
                            "request_id": None,
                            "success": False,
                            "data": {},
                            "error": "Malformed JSON payload",
                        },
                    )
                    continue
                await dispatcher.handle(websocket, msg)
        except Exception:
            event_manager.disconnect(websocket)

    return app


def test_malformed_json_returns_command_response():
    dispatcher = CommandDispatcher()
    app = _make_ws_app(dispatcher)

    with TestClient(app).websocket_connect("/ws/updates") as websocket:
        websocket.send_text("{not-valid-json")
        response = websocket.receive_json()

    assert response["type"] == "command_response"
    assert response["success"] is False
    assert response["error"] == "Malformed JSON payload"


def test_unknown_action_returns_error_response():
    dispatcher = CommandDispatcher()
    app = _make_ws_app(dispatcher)

    with TestClient(app).websocket_connect("/ws/updates") as websocket:
        websocket.send_json({"action": "does_not_exist", "request_id": "req-1", "data": {}})
        response = websocket.receive_json()

    assert response["type"] == "command_response"
    assert response["request_id"] == "req-1"
    assert response["success"] is False
    assert "Unknown action" in response["error"]


def test_successful_dispatch_and_request_correlation():
    dispatcher = CommandDispatcher()

    async def _echo(data):
        return {"echo": data.get("value")}

    dispatcher.register("echo", _echo)
    app = _make_ws_app(dispatcher)

    with TestClient(app).websocket_connect("/ws/updates") as websocket:
        websocket.send_json(
            {
                "action": "echo",
                "request_id": "req-correlation-123",
                "data": {"value": "ok"},
            }
        )
        response = websocket.receive_json()

    assert response["type"] == "command_response"
    assert response["request_id"] == "req-correlation-123"
    assert response["success"] is True
    assert response["data"] == {"echo": "ok"}


def test_unicast_response_targets_requesting_socket_only():
    dispatcher = CommandDispatcher()

    async def _ok(_data):
        return {"done": True}

    dispatcher.register("ok", _ok)

    ws_one = _FakeWebSocket()
    ws_two = _FakeWebSocket()

    asyncio.run(dispatcher.handle(ws_one, {"action": "ok", "request_id": "r-1", "data": {}}))

    assert len(ws_one.messages) == 1
    assert ws_one.messages[0]["request_id"] == "r-1"
    assert ws_two.messages == []


def test_enqueue_submit_pipeline_job_sorts_phases_canonically(monkeypatch):
    captured: dict = {}

    def fake_enqueue_job_with_phases(
        input_path, phase_code=None, job_type=None, queue_payload=None,
        description=None, phase_codes=None, first_phase_state="queued",
    ):
        payload = queue_payload if isinstance(queue_payload, dict) else {}
        captured["payload_phases"] = list(payload.get("phases") or [])
        captured["phase_codes"] = list(phase_codes or [])
        return 42, 0

    monkeypatch.setattr("modules.db.enqueue_job_with_phases", fake_enqueue_job_with_phases)

    dispatcher = CommandDispatcher()
    asyncio.run(
        dispatcher._handle_submit_folder(
            {
                "targetPaths": ["/tmp/scope"],
                "jobType": "pipeline",
                "options": {},
            }
        )
    )

    expected = sort_phase_value_strings(["indexing", "metadata", "scoring", "keywords", "culling"])
    assert captured["payload_phases"] == expected
    assert captured["phase_codes"] == expected


def test_get_status_clustering_runner_four_tuple():
    """ClusteringRunner.get_status returns (is_running, status_message, current, total)."""

    class _ClusterLike:
        def get_status(self):
            return True, "Working", 3, 10

    dispatcher = CommandDispatcher()
    dispatcher.set_runners(clustering_runner=_ClusterLike())

    async def _run():
        return await dispatcher._handle_get_status({})

    out = asyncio.run(_run())
    assert out["clustering"]["available"] is True
    assert out["clustering"]["is_running"] is True
    assert out["clustering"]["status_message"] == "Working"
    assert out["clustering"]["progress"] == {"current": 3, "total": 10}
