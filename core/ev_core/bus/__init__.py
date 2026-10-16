"""In-process async event bus (docs/ARCHITECTURE.md §4.2).

Handlers are matched on the exact event type. Each handler runs as its own
task; a failing handler is logged and never affects the publisher or other
handlers.
"""

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Event:
    """Base class for bus events. Subclasses are frozen dataclasses."""


type Handler[E: Event] = Callable[[E], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: defaultdict[type[Event], list[Handler[Any]]] = defaultdict(list)
        self._tasks: set[asyncio.Task[None]] = set()

    def subscribe[E: Event](self, event_type: type[E], handler: Handler[E]) -> Callable[[], None]:
        """Register ``handler`` for ``event_type``; returns a function that unsubscribes it."""
        self._handlers[event_type].append(handler)

        def unsubscribe() -> None:
            handlers = self._handlers[event_type]
            if handler in handlers:
                handlers.remove(handler)

        return unsubscribe

    def publish(self, event: Event) -> None:
        """Schedule every handler of ``type(event)``. Must be called from the event loop."""
        for handler in list(self._handlers[type(event)]):
            task = asyncio.create_task(self._run(handler, event))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def drain(self) -> None:
        """Wait until every scheduled handler has finished."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks))

    @staticmethod
    async def _run(handler: Handler[Any], event: Event) -> None:
        try:
            await handler(event)
        except Exception:
            logger.exception(
                "event handler failed",
                extra={"fields": {"event": type(event).__name__, "handler": repr(handler)}},
            )
