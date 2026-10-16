import asyncio

import pytest

from ev_core.bus import EventBus
from ev_core.errors import EvError
from ev_core.modules import (
    DISABLED_DETAIL,
    FAILED_DETAIL,
    TIMEOUT_DETAIL,
    Module,
    ModuleContext,
    ModuleRegistry,
    ModuleState,
    ModuleStatus,
)


class FakeModule(Module):
    def __init__(self, name: str, *, fail: BaseException | None = None, hang: bool = False) -> None:
        self.name = name  # type: ignore[misc]
        self._fail = fail
        self._hang = hang
        self.started = False
        self.stopped = False
        self.log: list[str] | None = None

    async def start(self, ctx: ModuleContext) -> None:
        assert ctx.logger.name == f"ev_core.module.{self.name}"
        if self._hang:
            await asyncio.sleep(10)
        if self._fail is not None:
            raise self._fail
        self.started = True

    async def stop(self) -> None:
        self.stopped = True
        if self.log is not None:
            self.log.append(self.name)


async def test_states_for_each_outcome() -> None:
    registry = ModuleRegistry(EventBus(), start_timeout_s=0.05)
    registry.register(FakeModule("ok"), enabled=True)
    registry.register(FakeModule("off"), enabled=False)
    registry.register(FakeModule("typed", fail=EvError("Microphone not found.")), enabled=True)
    registry.register(FakeModule("crash", fail=RuntimeError("x")), enabled=True)
    registry.register(FakeModule("slow", hang=True), enabled=True)

    await registry.start_all()

    assert registry.statuses() == [
        ModuleStatus("ok", ModuleState.READY),
        ModuleStatus("off", ModuleState.DISABLED, DISABLED_DETAIL),
        ModuleStatus("typed", ModuleState.FAILED, "Microphone not found."),
        ModuleStatus("crash", ModuleState.FAILED, FAILED_DETAIL),
        ModuleStatus("slow", ModuleState.FAILED, TIMEOUT_DETAIL),
    ]


async def test_statuses_are_starting_before_start() -> None:
    registry = ModuleRegistry(EventBus())
    registry.register(FakeModule("a"), enabled=True)
    assert registry.statuses() == [ModuleStatus("a", ModuleState.STARTING)]


def test_duplicate_name_rejected() -> None:
    registry = ModuleRegistry(EventBus())
    registry.register(FakeModule("a"), enabled=True)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(FakeModule("a"), enabled=True)


async def test_stop_only_ready_in_reverse_order() -> None:
    log: list[str] = []
    registry = ModuleRegistry(EventBus())
    modules = [FakeModule("a"), FakeModule("b", fail=RuntimeError()), FakeModule("c")]
    for module in modules:
        module.log = log
        registry.register(module, enabled=True)
    await registry.start_all()
    await registry.stop_all()
    assert log == ["c", "a"]


async def test_stop_error_is_logged_not_raised(caplog: pytest.LogCaptureFixture) -> None:
    class BadStop(FakeModule):
        async def stop(self) -> None:
            raise RuntimeError("stop failed")

    registry = ModuleRegistry(EventBus())
    registry.register(BadStop("x"), enabled=True)
    await registry.start_all()
    await registry.stop_all()
    assert any(r.message == "module stop failed" for r in caplog.records)


def test_state_values_match_protocol() -> None:
    from ev_core.protocol import ModuleState as WireState

    assert {s.value for s in ModuleState} == {s.value for s in WireState}
