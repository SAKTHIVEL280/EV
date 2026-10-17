"""Children never outlive core (ev_core.platform.children)."""

import subprocess
import sys
import time
from pathlib import Path

import pytest

from ev_core.platform.children import ChildGuard

SLEEPER = [sys.executable, "-c", "import time; time.sleep(60)"]


def _wait_exec(pid: int, timeout_s: float = 10) -> None:
    """Wait until `setpriv` has armed the death signal and exec'd the real child.

    The kernel arms the signal only when setpriv runs; killing the parent before
    that leaves the child running (the CI runner hit this window).
    """
    import psutil

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if Path(psutil.Process(pid).exe()).name != "setpriv":
            return
        time.sleep(0.01)
    raise AssertionError("setpriv never exec'd the child")


def _wait_dead(pid: int, timeout_s: float = 10) -> bool:
    import psutil

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if psutil.Process(pid).status() == psutil.STATUS_ZOMBIE:
                return True
        except psutil.NoSuchProcess:
            # Gone between checks is the outcome we wait for, not an error.
            return True
        time.sleep(0.05)
    return False


@pytest.mark.skipif(sys.platform != "linux", reason="setpriv --pdeathsig is Linux-only")
def test_linux_child_dies_with_parent(tmp_path: Path) -> None:
    # A parent process spawns a guarded child, prints its pid, then is killed.
    script = tmp_path / "parent.py"
    script.write_text(
        "import subprocess, sys, time\n"
        "from ev_core.platform.children import ChildGuard\n"
        f"guard = ChildGuard()\n"
        f"child = subprocess.Popen(guard.command({SLEEPER!r}), **guard.spawn_kwargs())\n"
        "print(child.pid, flush=True)\n"
        "time.sleep(60)\n"
    )
    parent = subprocess.Popen([sys.executable, str(script)], stdout=subprocess.PIPE, text=True)  # noqa: S603
    assert parent.stdout is not None
    with parent.stdout:
        child_pid = int(parent.stdout.readline())
    _wait_exec(child_pid)
    parent.kill()
    parent.wait()
    assert _wait_dead(child_pid)


@pytest.mark.skipif(sys.platform != "win32", reason="Job Objects are Windows-only")
def test_windows_closing_the_job_kills_children() -> None:
    guard = ChildGuard()
    child = subprocess.Popen(SLEEPER, **guard.spawn_kwargs())  # noqa: S603
    guard.adopt(child.pid)
    guard.close()
    assert child.wait(timeout=10) is not None


@pytest.mark.skipif(sys.platform != "linux", reason="Linux wrapping")
def test_linux_command_is_wrapped_with_setpriv() -> None:
    wrapped = ChildGuard().command(["llama-server", "--port", "1"])
    assert wrapped[1:4] == ["--pdeathsig", "KILL", "--"]
    assert wrapped[-3:] == ["llama-server", "--port", "1"]
