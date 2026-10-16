import asyncio
from dataclasses import dataclass

import pytest

from ev_core.bus import Event, EventBus


@dataclass(frozen=True, slots=True)
class Ping(Event):
    n: int


@dataclass(frozen=True, slots=True)
class Other(Event):
    pass


async def test_publish_reaches_subscribers_of_exact_type() -> None:
    bus = EventBus()
    seen: list[int] = []

    async def handler(event: Ping) -> None:
        seen.append(event.n)

    async def other(_: Other) -> None:
        seen.append(-1)

    bus.subscribe(Ping, handler)
    bus.subscribe(Other, other)
    bus.publish(Ping(1))
    await bus.drain()
    assert seen == [1]


async def test_failing_handler_is_isolated_and_logged(caplog: pytest.LogCaptureFixture) -> None:
    bus = EventBus()
    seen: list[int] = []

    async def bad(_: Ping) -> None:
        raise RuntimeError("boom")

    async def good(event: Ping) -> None:
        seen.append(event.n)

    bus.subscribe(Ping, bad)
    bus.subscribe(Ping, good)
    bus.publish(Ping(7))
    await bus.drain()
    assert seen == [7]
    assert any(r.message == "event handler failed" and r.exc_info for r in caplog.records)


async def test_unsubscribe() -> None:
    bus = EventBus()
    seen: list[int] = []

    async def handler(event: Ping) -> None:
        seen.append(event.n)

    unsubscribe = bus.subscribe(Ping, handler)
    unsubscribe()
    unsubscribe()  # idempotent
    bus.publish(Ping(1))
    await bus.drain()
    assert seen == []


async def test_drain_returns_when_finished_tasks_await_cleanup() -> None:
    # A handler that finishes immediately leaves its task in the set until the
    # discard callback runs; drain must not spin on it.
    bus = EventBus()
    seen: list[int] = []

    async def handler(event: Ping) -> None:
        seen.append(event.n)

    bus.subscribe(Ping, handler)
    bus.publish(Ping(1))
    await asyncio.sleep(0)  # the handler task runs and finishes; cleanup is only scheduled
    await asyncio.wait_for(bus.drain(), 1)
    assert seen == [1]
