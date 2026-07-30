"""
runtime/event_bus.py — Lightweight publish/subscribe event system.

Enables decoupled communication between modules without direct imports.
Handlers run synchronously in the publisher's thread by default.

Basic usage:
    from onyx.runtime.event_bus import bus

    def on_tool_done(data):
        print(f"Tool finished: {data}")

    bus.subscribe("tool.executed", on_tool_done)
    bus.publish("tool.executed", {"name": "open_app", "result": "ok"})
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

logger = logging.getLogger(__name__)


class EventBus:
    """In-process publish/subscribe event bus.

    Thread-safe. Each topic can have multiple handlers.
    A single handler failure does not affect other handlers
    for the same topic.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subscribers: dict[str, list[Callable[[Any], None]]] = {}

    # ── Public API ────────────────────────────────────────────────────────

    def subscribe(self, topic: str, handler: Callable[[Any], None]) -> None:
        """Register *handler* to be called when *topic* is published."""
        if not callable(handler):
            raise TypeError("handler must be callable")
        with self._lock:
            self._subscribers.setdefault(topic, []).append(handler)

    def unsubscribe(self, topic: str, handler: Callable[[Any], None]) -> None:
        """Remove a previously registered *handler* from *topic*."""
        with self._lock:
            handlers = self._subscribers.get(topic)
            if handlers:
                try:
                    handlers.remove(handler)
                except ValueError:
                    pass

    def publish(self, topic: str, data: Any = None) -> None:
        """Call every handler registered for *topic* with *data*.

        Exceptions raised by a handler are caught and logged so that
        one misbehaving subscriber cannot break the entire bus.
        """
        with self._lock:
            handlers = list(self._subscribers.get(topic, []))
        for handler in handlers:
            try:
                handler(data)
            except Exception:
                logger.exception(
                    "EventBus: handler %r failed for topic %r", handler, topic
                )

    def clear(self) -> None:
        """Remove all subscribers from every topic."""
        with self._lock:
            self._subscribers.clear()

    @property
    def topics(self) -> list[str]:
        """Return the list of topics that currently have subscribers."""
        with self._lock:
            return list(self._subscribers.keys())


# Singleton — importable from any module.
bus = EventBus()
