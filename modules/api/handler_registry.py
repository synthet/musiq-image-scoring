"""Registry for route handlers shared across routers (IPC bridge dispatch)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

_HANDLERS: dict[str, Callable[..., Any]] = {}


def register_handlers(mapping: dict[str, Callable[..., Any]]) -> None:
    _HANDLERS.update(mapping)


def get_handler(name: str) -> Callable[..., Any]:
    try:
        return _HANDLERS[name]
    except KeyError as exc:
        raise KeyError(f"API handler not registered: {name}") from exc
