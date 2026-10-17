"""Picks the PC control for this platform (docs/FEATURES.md Phase 3)."""

import sys
from pathlib import Path

from ev_core.interfaces.pc import PcControl


def make_pc_control(data_dir: Path) -> PcControl:
    """Windows: the real thing. Elsewhere (development): the fake, whose files
    live in `dev-home` inside EV's data folder, never in the developer's home."""
    if sys.platform == "win32":
        from ev_core.platform.windows_pc import WindowsPcControl

        return WindowsPcControl()
    from ev_core.platform.fake_pc import FakePcControl

    return FakePcControl(data_dir / "dev-home")
