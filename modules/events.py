import asyncio
import datetime
import json
import logging
import threading
from typing import Any

from pydantic import BaseModel, Field

try:
    from fastapi import WebSocket, WebSocketDisconnect
except ImportError:
    WebSocket = Any
    WebSocketDisconnect = Exception

logger = logging.getLogger(__name__)


class WebSocketEvent(BaseModel):
    """Schema for WebSocket push events broadcast to clients."""

    type: str
    data: dict = Field(default_factory=dict)


class EventManager:
    """
    Manages WebSocket connections and broadcasts events to connected clients.
    """
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.loop = None
        self._connections_lock = threading.RLock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        with self._connections_lock:
            self.active_connections.append(websocket)
            n = len(self.active_connections)
        logger.info("Client connected. Total connections: %d", n)

    async def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket from active connections (thread-safe)."""
        with self._connections_lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
                n = len(self.active_connections)
            else:
                return
        logger.info("Client disconnected. Total connections: %d", n)

    def disconnect_sync(self, websocket: WebSocket):
        """Synchronous version for cleanup from non-async contexts."""
        with self._connections_lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
                n = len(self.active_connections)
            else:
                return
        logger.info("Client disconnected. Total connections: %d", n)

    async def broadcast(self, event_type: str, data: Any = None):
        """
        Broadcasts an event to all connected clients.
        """
        message = {
            "type": event_type,
            "data": data or {}
        }
        json_message = json.dumps(message)
        
        logger.debug(f"Broadcasting event: {event_type}")
        
        # Snapshot under lock so disconnect_sync / other threads cannot mutate mid-copy
        with self._connections_lock:
            connections = self.active_connections[:]
        
        for connection in connections:
            try:
                await connection.send_text(json_message)
            except Exception as e:
                logger.error(f"Failed to send message to client: {e}")
                await self.disconnect(connection)

    async def send_to(self, websocket: WebSocket, message: dict[str, Any]):
        """Send a JSON-serializable message to a specific WebSocket client."""
        try:
            await websocket.send_text(json.dumps(message))
        except Exception as e:
            logger.error(f"Failed to send unicast message to client: {e}")
            await self.disconnect(websocket)

    def broadcast_threadsafe(self, event_type: str, data: Any = None):
        """
        Broadcasts an event from a separate thread.

        Requires ``set_loop`` to have been called with the FastAPI/uvicorn event loop
        (see ``webui.py`` lifespan). Without it, broadcasts are skipped and a warning is logged.
        """
        loop = getattr(self, "loop", None)
        if loop and not loop.is_closed():
            asyncio.run_coroutine_threadsafe(self.broadcast(event_type, data), loop)
        else:
            logger.warning("No event loop attached to EventManager, skipping broadcast.")

    def set_loop(self, loop):
        self.loop = loop


# Global instance (defined before broadcast_run_log_line so helpers can reference it)
event_manager = EventManager()


def broadcast_run_log_line(run_id: int, message: str, level: str = "INFO") -> None:
    """Push one run-scoped log line to WebSocket clients (React /ui/runs detail)."""
    try:
        ts = (
            datetime.datetime.now(datetime.timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
        event_manager.broadcast_threadsafe(
            "log_line",
            {"run_id": int(run_id), "level": level, "message": str(message), "ts": ts},
        )
    except Exception:
        pass
