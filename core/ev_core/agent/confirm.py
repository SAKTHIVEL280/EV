"""Asks the user before confirm/dangerous steps (docs/FEATURES.md F-418).

The question goes out as `ToolConfirmRequested`; the island answers with
`ToolAnswered`. No answer within the timeout counts as no. The question is
always closed with `ToolConfirmClosed`, so the island never keeps a stale one.
"""

import asyncio
import contextlib
import logging
import uuid
from typing import Final, Protocol

from ev_core.bus import EventBus
from ev_core.interfaces.events import ToolAnswered, ToolConfirmClosed, ToolConfirmRequested
from ev_core.interfaces.tools import Risk

logger = logging.getLogger(__name__)

ANSWER_TIMEOUT_S: Final = 60.0


class Confirmer(Protocol):
    async def ask(self, turn_id: str, tool: str, question: str, risk: Risk) -> bool: ...


class Confirmations:
    def __init__(self, bus: EventBus, timeout_s: float = ANSWER_TIMEOUT_S) -> None:
        self._bus = bus
        self._timeout_s = timeout_s
        self._pending: dict[str, asyncio.Future[bool]] = {}
        bus.subscribe(ToolAnswered, self._on_answer)

    async def ask(self, turn_id: str, tool: str, question: str, risk: Risk) -> bool:
        request_id = str(uuid.uuid4())
        future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        self._bus.publish(ToolConfirmRequested(turn_id, request_id, tool, question, risk.value))
        allowed = False
        try:
            async with asyncio.timeout(self._timeout_s):
                allowed = await future
        except TimeoutError:
            logger.info("confirmation timed out", extra={"fields": {"tool": tool}})
        finally:
            self._pending.pop(request_id, None)
            self._bus.publish(ToolConfirmClosed(request_id, allowed))
        return allowed

    async def _on_answer(self, event: ToolAnswered) -> None:
        future = self._pending.get(event.request_id)
        if future is not None and not future.done():
            with contextlib.suppress(asyncio.InvalidStateError):
                future.set_result(event.allowed)
