"""Tests for WebSocket event manager. Uses a minimal FastAPI app to avoid importing full webui (Gradio, TF)."""
import pytest
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from modules.events import event_manager
import threading
import queue


def _make_ws_app():
    """Minimal FastAPI app with /ws/updates only. Avoids webui import (Gradio, TensorFlow)."""

    @asynccontextmanager
    async def lifespan(app):
        loop = asyncio.get_running_loop()
        event_manager.set_loop(loop)
        yield

    app = FastAPI(lifespan=lifespan)

    @app.websocket("/ws/updates")
    async def websocket_endpoint(websocket: WebSocket):
        await event_manager.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except Exception:
            event_manager.disconnect(websocket)

    return app


@pytest.fixture
def ws_client():
    with TestClient(_make_ws_app()) as client:
        yield client


def test_websocket_connection(ws_client):
    """Connect via WebSocket and receive a broadcast."""
    with ws_client.websocket_connect("/ws/updates") as websocket:
        assert len(event_manager.active_connections) == 1

        test_data = {"test": "data"}
        event_manager.broadcast_threadsafe("test_event", test_data)

        q: "queue.Queue[dict]" = queue.Queue()

        def _recv():
            try:
                q.put(websocket.receive_json())
            except Exception as e:
                q.put({"_error": repr(e)})

        t = threading.Thread(target=_recv, daemon=True)
        t.start()
        data = q.get(timeout=5)
        assert "_error" not in data, data["_error"]
        assert data["type"] == "test_event"
        assert data["data"] == test_data


def test_threadsafe_broadcast():
    """Ensure broadcast_threadsafe does not crash when no loop is set."""
    event_manager.broadcast_threadsafe("test_thread", {})
